"""
Doctor leave conflict resolution engine.

When a doctor is marked on leave, this module:
1. Finds all waiting/pending queue entries within the leave date range.
2. Marks them as 'cancelled' (status = 'cancelled').
3. Enqueues a high-priority leave_cancellation notification for each affected patient.

Non-blocking: notification failures are logged but do not prevent cancellation.
"""

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import get_logger
from src.models.integration import Notification
from src.models.queue import DoctorQueue
from src.models.user import User

logger = get_logger(__name__)

CANCELLABLE_STATUSES = {"pending", "waiting"}


async def resolve_leave_conflicts(
    session: AsyncSession,
    doctor_id: int,
    start_date: date,
    end_date: date,
) -> list[DoctorQueue]:
    """
    Cancel all pending/waiting queue entries within the leave date range
    and enqueue leave_cancellation notifications for affected patients.

    Args:
        session: Async DB session (already in a transaction).
        doctor_id: The doctor going on leave.
        start_date: First day of leave (inclusive).
        end_date: Last day of leave (inclusive).

    Returns:
        List of DoctorQueue entries that were cancelled.
    """
    # Fetch all affected queue entries
    result = await session.execute(
        select(DoctorQueue).where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date >= start_date,
            DoctorQueue.appointment_date <= end_date,
            DoctorQueue.status.in_(CANCELLABLE_STATUSES),
        )
    )
    affected_entries = result.scalars().all()

    if not affected_entries:
        logger.info(
            "No affected appointments for doctor_id=%s leave=%s to %s",
            doctor_id, start_date, end_date,
        )
        return []

    cancelled_ids = [e.id for e in affected_entries]
    patient_ids = list({e.patient_id for e in affected_entries if e.patient_id})

    # Bulk cancel all affected entries
    await session.execute(
        update(DoctorQueue)
        .where(DoctorQueue.id.in_(cancelled_ids))
        .values(status="cancelled")
    )
    logger.info(
        "Cancelled %d appointments for doctor_id=%s (leave %s to %s)",
        len(cancelled_ids), doctor_id, start_date, end_date,
    )

    # Fetch patient details for notifications
    patients_result = await session.execute(
        select(User).where(User.id.in_(patient_ids))
    )
    patients = {u.id: u for u in patients_result.scalars().all()}

    # Enqueue leave_cancellation notifications for each affected patient
    notifications_created = 0
    for entry in affected_entries:
        if entry.patient_id is None:
            continue
        patient = patients.get(entry.patient_id)
        if patient is None:
            continue

        # Prefer WhatsApp for real-time leave alerts
        if patient.whatsapp_number:
            _enqueue_notification(
                session=session,
                notification_type="leave_cancellation",
                channel="whatsapp",
                recipient_id=patient.id,
                queue_id=entry.id,
                destination=patient.whatsapp_number,
            )
            notifications_created += 1

        # Always send formal Email record
        if patient.email:
            _enqueue_notification(
                session=session,
                notification_type="leave_cancellation",
                channel="email",
                recipient_id=patient.id,
                queue_id=entry.id,
                destination=patient.email,
            )
            notifications_created += 1

    logger.info(
        "Enqueued %d leave_cancellation notifications for doctor_id=%s",
        notifications_created, doctor_id,
    )

    await session.flush()

    # Return the list of cancelled entries (caller may use for further processing)
    return list(affected_entries)


def _enqueue_notification(
    *,
    session: AsyncSession,
    notification_type: str,
    channel: str,
    recipient_id: int,
    queue_id: int,
    destination: str,
) -> None:
    """Add a pending notification record to the session (not yet committed)."""
    notification = Notification(
        type=notification_type,
        channel=channel,
        recipient_id=recipient_id,
        queue_id=queue_id,
        destination=destination,
        status="pending",
    )
    session.add(notification)
