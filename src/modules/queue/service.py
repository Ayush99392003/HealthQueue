"""
Token booking service — SERIALIZABLE transaction with pessimistic locking.

Invariants (AGENTS.md):
- token_number is assigned atomically; never reused or inferred from serving order.
- SERIALIZABLE isolation + SELECT ... FOR UPDATE prevents double-booking.
- Concurrency collisions retry up to 3 times before raising ConflictError (409).
"""

import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import InternalError, OperationalError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from src.core.database import get_serializable_session
from src.core.exceptions import ConflictError, DoctorNotAvailableError, QueueFullError
from src.core.logger import get_logger
from src.models.doctor import Doctor, DoctorLeave
from src.models.queue import DoctorQueue
from src.modules.queue.engine import recalculate_display_positions

logger = get_logger(__name__)


@retry(
    retry=retry_if_exception_type((OperationalError, InternalError)),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.5, max=3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def book_token(
    *,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
    patient_id: int,
    tier: str = "regular",
    slot_type: str = "open",
    anchor_time: str | None = None,
    booking_mode_used: str = "advance",
) -> DoctorQueue:
    """
    Book a token slot inside a SERIALIZABLE transaction with FOR UPDATE locking.

    The function:
    1. Verifies doctor exists and is not on leave for the requested date.
    2. Acquires a SERIALIZABLE session and locks the doctor's queue row.
    3. Assigns the next sequential token_number atomically.
    4. Creates the DoctorQueue record and recalculates display_positions.

    Retries up to 3 times on serialization collisions (OperationalError).
    Raises ConflictError if all retries are exhausted.

    Args:
        doctor_id: The doctor's user ID.
        appointment_date: Date of the appointment.
        queue_session: "morning" | "evening" | "full_day"
        patient_id: The booking patient's user ID.
        tier: "regular" | "priority" | "emergency"
        slot_type: "open" | "anchor"
        anchor_time: Required if slot_type="anchor" (HH:MM format).
        booking_mode_used: Snapshot of booking mode at time of booking.

    Returns:
        The newly created DoctorQueue entry.

    Raises:
        DoctorNotAvailableError: Doctor on leave or not configured for requested date.
        QueueFullError: No more token slots available for this session.
        ConflictError: All concurrency retries exhausted.
    """
    async with get_serializable_session() as session:
        async with session.begin():
            # ── Validate doctor exists ─────────────────────────────────
            doctor_result = await session.execute(
                select(Doctor).where(Doctor.id == doctor_id)
            )
            doctor = doctor_result.scalar_one_or_none()
            if doctor is None:
                raise DoctorNotAvailableError(
                    f"Doctor {doctor_id} not found"
                )

            # ── Check leave conflict ───────────────────────────────────
            leave_result = await session.execute(
                select(DoctorLeave).where(
                    DoctorLeave.doctor_id == doctor_id,
                    DoctorLeave.start_date <= appointment_date,
                    DoctorLeave.end_date >= appointment_date,
                )
            )
            if leave_result.scalar_one_or_none():
                raise DoctorNotAvailableError(
                    f"Doctor {doctor_id} is on approved leave on {appointment_date}"
                )

            # ── Lock the queue for this doctor/date/session ───────────
            await session.execute(
                select(DoctorQueue)
                .where(
                    DoctorQueue.doctor_id == doctor_id,
                    DoctorQueue.appointment_date == appointment_date,
                    DoctorQueue.session == queue_session,
                )
                .with_for_update()
                .limit(1)
            )

            # ── Assign next sequential token_number ───────────────────
            max_token_result = await session.execute(
                select(func.max(DoctorQueue.token_number)).where(
                    DoctorQueue.doctor_id == doctor_id,
                    DoctorQueue.appointment_date == appointment_date,
                    DoctorQueue.session == queue_session,
                )
            )
            max_token = max_token_result.scalar_one_or_none() or 0
            new_token_number = max_token + 1

            logger.info(
                "Assigning token_number=%d — doctor_id=%s date=%s session=%s patient_id=%s",
                new_token_number,
                doctor_id,
                appointment_date,
                queue_session,
                patient_id,
            )

            # ── Create queue entry ────────────────────────────────────
            queue_entry = DoctorQueue(
                doctor_id=doctor_id,
                appointment_date=appointment_date,
                session=queue_session,
                token_number=new_token_number,
                patient_id=patient_id,
                tier=tier,
                slot_type=slot_type,
                anchor_time=anchor_time,
                status="waiting",
                booking_mode_used=booking_mode_used,
            )
            session.add(queue_entry)
            await session.flush()  # Get the ID before commit

            # ── Recalculate all display_positions ─────────────────────
            await recalculate_display_positions(
                session, doctor_id, appointment_date, queue_session
            )

            logger.info(
                "Token booked successfully — queue_id=%s token_number=%d",
                queue_entry.id,
                new_token_number,
            )
            return queue_entry
