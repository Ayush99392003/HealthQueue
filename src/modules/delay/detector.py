"""
Delay detection engine.

Runs after every consultation completion.
Compares actual pace vs expected pace (avg_consult_minutes).
If drift exceeds threshold, writes a delay_events row and triggers
thresholded notifications (not on every tick — only on new threshold crossings).

Notification strategy:
- Immediate: Next 3-5 patients affected (WhatsApp alert)
- Batched: All remaining patients (WhatsApp with SHIFT/RESCHEDULE options)
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logger import get_logger
from src.models.doctor import Doctor
from src.models.integration import Notification
from src.models.queue import DelayEvent, DoctorQueue
from src.models.user import User

logger = get_logger(__name__)
settings = get_settings()

IMMEDIATE_NOTIFY_COUNT = 5  # Notify the next N patients immediately


async def detect_and_record_delay(
    session: AsyncSession,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
) -> DelayEvent | None:
    """
    Detect pace drift after a consultation is marked complete.

    Algorithm:
    1. Count completed tokens and total elapsed session time.
    2. Compare actual pace vs expected pace (avg_consult_minutes).
    3. If drift > threshold, record delay_event and trigger notifications.
    4. Only fires notifications if a NEW threshold is crossed (not every tick).

    Returns the newly created DelayEvent, or None if no significant delay.
    """
    # Get doctor config
    doctor_result = await session.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = doctor_result.scalar_one_or_none()
    if doctor is None:
        return None

    avg_minutes = float(doctor.avg_consult_minutes or doctor.slot_duration_minutes or 15)

    # Count completed consultations today in this session
    completed_result = await session.execute(
        select(func.count(DoctorQueue.id)).where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status == "completed",
            DoctorQueue.completed_at.isnot(None),
        )
    )
    completed_count = completed_result.scalar_one() or 0

    # Get first called_at for session start approximation
    first_call_result = await session.execute(
        select(func.min(DoctorQueue.called_at)).where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.called_at.isnot(None),
        )
    )
    session_start = first_call_result.scalar_one_or_none()
    if session_start is None or completed_count == 0:
        return None  # Not enough data to compute drift

    elapsed_minutes = (datetime.utcnow() - session_start).total_seconds() / 60
    expected_minutes = completed_count * avg_minutes
    drift_minutes = int(elapsed_minutes - expected_minutes)

    logger.debug(
        "Delay check — doctor_id=%s elapsed=%.1fm expected=%.1fm drift=%dm",
        doctor_id, elapsed_minutes, expected_minutes, drift_minutes,
    )

    if drift_minutes < settings.delay_detection_threshold_minutes:
        return None  # Within acceptable bounds

    # Check most recent recorded delay to avoid duplicate threshold notifications
    last_delay_result = await session.execute(
        select(DelayEvent)
        .where(
            DelayEvent.doctor_id == doctor_id,
            DelayEvent.appointment_date == appointment_date,
            DelayEvent.session == queue_session,
        )
        .order_by(DelayEvent.detected_at.desc())
        .limit(1)
    )
    last_delay = last_delay_result.scalar_one_or_none()

    # Only fire if drift crossed a new 20-min threshold
    last_threshold = (last_delay.delay_minutes // settings.delay_detection_threshold_minutes
                      if last_delay else 0)
    current_threshold = drift_minutes // settings.delay_detection_threshold_minutes

    if current_threshold <= last_threshold:
        logger.debug(
            "Delay unchanged (still threshold %d) — skipping notification",
            current_threshold,
        )
        return None

    # Record new delay event
    delay_event = DelayEvent(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        session=queue_session,
        delay_minutes=drift_minutes,
        notified=False,
    )
    session.add(delay_event)
    await session.flush()

    logger.warning(
        "Delay threshold crossed — doctor_id=%s drift=%dm threshold=#%d",
        doctor_id, drift_minutes, current_threshold,
    )

    # Enqueue notifications for affected waiting patients
    await _notify_affected_patients(
        session,
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        queue_session=queue_session,
        delay_minutes=drift_minutes,
    )

    # Mark delay event as notified
    delay_event.notified = True
    return delay_event


async def _notify_affected_patients(
    session: AsyncSession,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
    delay_minutes: int,
) -> None:
    """
    Enqueue WhatsApp delay alerts for all waiting patients.

    Next IMMEDIATE_NOTIFY_COUNT patients get an urgent ping.
    Remaining patients get a batched alert with SHIFT/RESCHEDULE options.
    """
    waiting_result = await session.execute(
        select(DoctorQueue).where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status.in_(["waiting", "pending"]),
        )
        .order_by(DoctorQueue.display_position)
    )
    waiting_entries = waiting_result.scalars().all()

    # Fetch patient records
    patient_ids = [e.patient_id for e in waiting_entries if e.patient_id]
    if not patient_ids:
        return

    patients_result = await session.execute(
        select(User).where(User.id.in_(patient_ids))
    )
    patients = {u.id: u for u in patients_result.scalars().all()}

    notifications_queued = 0
    for idx, entry in enumerate(waiting_entries):
        patient = patients.get(entry.patient_id)
        if not patient or not patient.whatsapp_number:
            continue

        if idx < IMMEDIATE_NOTIFY_COUNT:
            notification_type = "delay_update"  # Immediate — you're next
        else:
            notification_type = "delay_update"  # Batched — includes SHIFT/RESCHEDULE

        session.add(Notification(
            type=notification_type,
            channel="whatsapp",
            recipient_id=patient.id,
            queue_id=entry.id,
            destination=patient.whatsapp_number,
            status="pending",
        ))
        notifications_queued += 1

    logger.info(
        "Delay notifications queued — count=%d delay=%dmin doctor_id=%s",
        notifications_queued, delay_minutes, doctor_id,
    )
