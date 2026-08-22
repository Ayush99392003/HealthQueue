"""
Doctor management service — CRUD for doctors, availability, and leave.

Handles:
- Doctor profile creation and updates
- Availability schedule configuration
- Leave marking with conflict detection
"""

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logger import get_logger
from src.models.doctor import Doctor, DoctorAvailability, DoctorLeave
from src.models.user import User

logger = get_logger(__name__)

VALID_SESSIONS = {"morning", "evening", "full_day"}
VALID_BOOKING_MODES = {"walk_in", "advance_only", "hybrid"}


async def create_doctor_profile(
    session: AsyncSession,
    user_id: int,
    *,
    specialisation: str,
    bio: str | None = None,
    experience_years: int | None = None,
    slot_duration_minutes: int = 15,
    booking_mode: str = "hybrid",
    anchor_slot_pct: float = 25.0,
    priority_slot_pct: float = 25.0,
    emergency_slot_pct: float = 10.0,
) -> Doctor:
    """
    Create a doctor profile for an existing user with role='doctor'.

    Raises:
        NotFoundError: User not found or not a doctor role.
        ConflictError: Doctor profile already exists for this user.
        ValidationError: booking_mode is invalid.
    """
    if booking_mode not in VALID_BOOKING_MODES:
        raise ValidationError(
            f"Invalid booking_mode: {booking_mode!r}. "
            f"Must be one of {sorted(VALID_BOOKING_MODES)}"
        )

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if user.role != "doctor":
        raise ValidationError(
            f"User {user_id} has role={user.role!r}. Only users with role='doctor' can have a doctor profile."
        )

    existing = await session.execute(select(Doctor).where(Doctor.id == user_id))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Doctor profile already exists for user {user_id}")

    doctor = Doctor(
        id=user_id,
        specialisation=specialisation,
        bio=bio,
        experience_years=experience_years,
        slot_duration_minutes=slot_duration_minutes,
        booking_mode=booking_mode,
        anchor_slot_pct=anchor_slot_pct,
        priority_slot_pct=priority_slot_pct,
        emergency_slot_pct=emergency_slot_pct,
    )
    session.add(doctor)
    await session.flush()

    logger.info(
        "Doctor profile created — doctor_id=%s specialisation=%s booking_mode=%s",
        user_id,
        specialisation,
        booking_mode,
    )
    return doctor


async def get_doctor(session: AsyncSession, doctor_id: int) -> Doctor:
    """
    Fetch a doctor by ID.

    Raises:
        NotFoundError: Doctor not found.
    """
    result = await session.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise NotFoundError(f"Doctor {doctor_id} not found")
    return doctor


async def set_availability(
    session: AsyncSession,
    doctor_id: int,
    *,
    day_of_week: int,
    session_name: str,
    start_time: str,
    end_time: str,
    is_working_day: bool = True,
) -> DoctorAvailability:
    """
    Set or update a doctor's availability for a specific day and session.

    Args:
        day_of_week: 0=Monday … 6=Sunday
        session_name: morning | evening | full_day

    Raises:
        ValidationError: Invalid day or session value.
        NotFoundError: Doctor not found.
    """
    from datetime import time as _time

    if not 0 <= day_of_week <= 6:
        raise ValidationError("day_of_week must be between 0 (Mon) and 6 (Sun)")
    if session_name not in VALID_SESSIONS:
        raise ValidationError(
            f"Invalid session: {session_name!r}. Must be one of {sorted(VALID_SESSIONS)}"
        )

    await get_doctor(session, doctor_id)  # Ensure doctor exists

    # Parse time strings
    try:
        start = _time.fromisoformat(start_time)
        end = _time.fromisoformat(end_time)
    except ValueError as exc:
        raise ValidationError(f"Invalid time format: {exc}") from exc

    if start >= end:
        raise ValidationError("start_time must be before end_time")

    # Upsert availability
    existing = await session.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.day_of_week == day_of_week,
            DoctorAvailability.session == session_name,
        )
    )
    availability = existing.scalar_one_or_none()

    if availability:
        availability.start_time = start
        availability.end_time = end
        availability.is_working_day = is_working_day
        logger.info(
            "Availability updated — doctor_id=%s day=%s session=%s",
            doctor_id, day_of_week, session_name,
        )
    else:
        availability = DoctorAvailability(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            session=session_name,
            start_time=start,
            end_time=end,
            is_working_day=is_working_day,
        )
        session.add(availability)
        logger.info(
            "Availability created — doctor_id=%s day=%s session=%s",
            doctor_id, day_of_week, session_name,
        )

    await session.flush()
    return availability


async def add_leave(
    session: AsyncSession,
    doctor_id: int,
    *,
    start_date: date,
    end_date: date,
    reason: str | None = None,
) -> DoctorLeave:
    """
    Mark a doctor on leave for a date range.

    Validates:
    - end_date >= start_date
    - No overlapping leave already exists

    Returns the newly created DoctorLeave record.
    The caller is responsible for triggering conflict resolution
    (cancelling affected appointments and notifying patients).
    """
    if end_date < start_date:
        raise ValidationError("end_date must be on or after start_date")

    await get_doctor(session, doctor_id)

    # Check for overlapping leave
    overlap_result = await session.execute(
        select(DoctorLeave).where(
            DoctorLeave.doctor_id == doctor_id,
            and_(
                DoctorLeave.start_date <= end_date,
                DoctorLeave.end_date >= start_date,
            ),
        )
    )
    if overlap_result.scalar_one_or_none():
        raise ConflictError(
            f"Doctor {doctor_id} already has an overlapping leave period "
            f"for {start_date} — {end_date}"
        )

    leave = DoctorLeave(
        doctor_id=doctor_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    session.add(leave)
    await session.flush()

    logger.info(
        "Doctor leave added — doctor_id=%s start=%s end=%s",
        doctor_id, start_date, end_date,
    )
    return leave


async def list_doctors(
    session: AsyncSession,
    specialisation: str | None = None,
    booking_mode: str | None = None,
) -> list[Doctor]:
    """List all active doctors with optional filters."""
    query = select(Doctor).join(User).where(User.is_active.is_(True))

    if specialisation:
        query = query.where(Doctor.specialisation.ilike(f"%{specialisation}%"))
    if booking_mode:
        query = query.where(Doctor.booking_mode == booking_mode)

    result = await session.execute(query)
    return list(result.scalars().all())
