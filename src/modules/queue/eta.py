"""
ETA and display_position calculation for the queue.

Estimates how long a patient will wait based on:
- Number of patients ahead in priority-ordered queue
- Doctor's rolling avg_consult_minutes (or slot_duration_minutes as fallback)
- Current delay (if a delay_event exists for today's session)
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import get_logger
from src.models.doctor import Doctor
from src.models.queue import DelayEvent, DoctorQueue

logger = get_logger(__name__)


async def calculate_eta(
    session: AsyncSession,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
    patient_queue_id: int,
) -> dict:
    """
    Calculate ETA and display_position for a specific patient's queue entry.

    Returns:
        {
            "display_position": int,        # live position in queue (1-indexed)
            "patients_ahead": int,          # count of patients ahead
            "estimated_wait_minutes": int,  # estimated minutes until called
            "eta_time": str | None,         # estimated clock time (HH:MM UTC)
            "current_delay_minutes": int,   # drift detected today (0 if none)
        }
    """
    # Fetch doctor for avg_consult_minutes
    doctor_result = await session.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = doctor_result.scalar_one_or_none()
    if doctor is None:
        logger.warning("ETA calc: doctor_id=%s not found", doctor_id)
        return _unknown_eta()

    avg_minutes = float(doctor.avg_consult_minutes or doctor.slot_duration_minutes or 15)

    # Fetch the patient's queue entry
    entry_result = await session.execute(
        select(DoctorQueue).where(DoctorQueue.id == patient_queue_id)
    )
    entry = entry_result.scalar_one_or_none()
    if entry is None or entry.display_position is None:
        return _unknown_eta()

    # Count patients ahead (lower display_position and waiting)
    ahead_result = await session.execute(
        select(DoctorQueue).where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status.in_(["waiting", "pending"]),
            DoctorQueue.display_position < entry.display_position,
        )
    )
    patients_ahead = len(ahead_result.scalars().all())

    # Check for current delay
    delay_result = await session.execute(
        select(DelayEvent)
        .where(
            DelayEvent.doctor_id == doctor_id,
            DelayEvent.appointment_date == appointment_date,
            DelayEvent.session == queue_session,
        )
        .order_by(DelayEvent.detected_at.desc())
        .limit(1)
    )
    latest_delay = delay_result.scalar_one_or_none()
    current_delay_minutes = latest_delay.delay_minutes if latest_delay else 0

    # ETA calculation
    wait_minutes = int(patients_ahead * avg_minutes + current_delay_minutes)
    eta_time = datetime.utcnow() + timedelta(minutes=wait_minutes)

    logger.debug(
        "ETA — queue_id=%s position=%s ahead=%d avg_min=%.1f delay=%d wait=%d min",
        patient_queue_id,
        entry.display_position,
        patients_ahead,
        avg_minutes,
        current_delay_minutes,
        wait_minutes,
    )

    return {
        "display_position": entry.display_position,
        "patients_ahead": patients_ahead,
        "estimated_wait_minutes": wait_minutes,
        "eta_time": eta_time.strftime("%H:%M") if wait_minutes > 0 else "Now",
        "current_delay_minutes": current_delay_minutes,
    }


def _unknown_eta() -> dict:
    return {
        "display_position": None,
        "patients_ahead": None,
        "estimated_wait_minutes": None,
        "eta_time": None,
        "current_delay_minutes": 0,
    }
