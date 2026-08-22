"""
Token queue engine — get_next_token() priority algorithm.

Priority order (AGENTS.md Invariant 3):
1. Emergency tier patients (waiting)
2. Anchor slots whose anchor_time has arrived (within grace window)
3. Priority tier patients (at configured ratio)
4. Regular FCFS open queue (booked_at order)
"""

from datetime import date, datetime, time

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import NotFoundError
from src.core.logger import get_logger
from src.models.queue import DoctorQueue

logger = get_logger(__name__)
settings = get_settings()


async def get_next_token(
    session: AsyncSession,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
) -> DoctorQueue | None:
    """
    Determine the next token to call based on strict priority hierarchy.

    This is called every time a doctor clicks "Complete & Call Next".
    Updates the selected token's status to 'in_progress' and sets called_at.

    Priority Order:
    1. Emergency tier (any waiting emergency patient)
    2. Anchor slot (anchor_time within grace window, doctor behind schedule)
    3. Priority tier (1-in-N ratio from settings.priority_serve_ratio)
    4. Regular FCFS (oldest booked_at)

    Returns:
        The next DoctorQueue entry to serve, or None if queue is empty.
    """
    now = datetime.utcnow()
    current_time = now.time()

    logger.info(
        "get_next_token called — doctor_id=%s date=%s session=%s",
        doctor_id,
        appointment_date,
        queue_session,
    )

    # ── 1. Emergency Tier ─────────────────────────────────────────────────────
    emergency_result = await session.execute(
        select(DoctorQueue)
        .where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status == "waiting",
            DoctorQueue.tier == "emergency",
        )
        .order_by(DoctorQueue.booked_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    emergency_token = emergency_result.scalar_one_or_none()

    if emergency_token:
        logger.info(
            "Emergency patient selected — token_id=%s token_number=%s",
            emergency_token.id,
            emergency_token.token_number,
        )
        return await _mark_in_progress(session, emergency_token, now)

    # ── 2. Anchor Slot (if anchor_time within grace window) ───────────────────
    grace_minutes = settings.anchor_slot_grace_window_minutes
    anchor_result = await session.execute(
        select(DoctorQueue)
        .where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status == "waiting",
            DoctorQueue.slot_type == "anchor",
            DoctorQueue.anchor_time.isnot(None),
        )
        .order_by(DoctorQueue.anchor_time)
        .limit(5)
        .with_for_update(skip_locked=True)
    )
    anchor_candidates = anchor_result.scalars().all()

    for anchor in anchor_candidates:
        if anchor.anchor_time is None:
            continue
        # Only pull anchor forward if its time has arrived (within grace window)
        anchor_dt = datetime.combine(appointment_date, anchor.anchor_time)
        minutes_since_anchor = (now - anchor_dt).total_seconds() / 60
        if minutes_since_anchor >= -grace_minutes:  # grace allows slight early start
            logger.info(
                "Anchor slot triggered — token_id=%s anchor_time=%s drift=%.1f min",
                anchor.id,
                anchor.anchor_time,
                minutes_since_anchor,
            )
            return await _mark_in_progress(session, anchor, now)

    # ── 3. Priority Tier (1-in-N ratio) ──────────────────────────────────────
    # Count recently completed tokens to determine if we should serve a priority patient
    completed_count_result = await session.execute(
        select(DoctorQueue)
        .where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status == "completed",
        )
    )
    completed_tokens = completed_count_result.scalars().all()
    completed_count = len(completed_tokens)

    should_serve_priority = (completed_count % settings.priority_serve_ratio == 0)

    if should_serve_priority:
        priority_result = await session.execute(
            select(DoctorQueue)
            .where(
                DoctorQueue.doctor_id == doctor_id,
                DoctorQueue.appointment_date == appointment_date,
                DoctorQueue.session == queue_session,
                DoctorQueue.status == "waiting",
                DoctorQueue.tier == "priority",
            )
            .order_by(DoctorQueue.booked_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        priority_token = priority_result.scalar_one_or_none()

        if priority_token:
            logger.info(
                "Priority patient selected (ratio slot %d) — token_id=%s",
                completed_count,
                priority_token.id,
            )
            return await _mark_in_progress(session, priority_token, now)

    # ── 4. Regular FCFS Open Queue ────────────────────────────────────────────
    regular_result = await session.execute(
        select(DoctorQueue)
        .where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status == "waiting",
            DoctorQueue.tier == "regular",
            DoctorQueue.slot_type == "open",
        )
        .order_by(DoctorQueue.booked_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    regular_token = regular_result.scalar_one_or_none()

    if regular_token:
        logger.info(
            "Regular FCFS patient selected — token_id=%s booked_at=%s",
            regular_token.id,
            regular_token.booked_at,
        )
        return await _mark_in_progress(session, regular_token, now)

    logger.info(
        "Queue empty — no waiting patients for doctor_id=%s date=%s session=%s",
        doctor_id,
        appointment_date,
        queue_session,
    )
    return None


async def _mark_in_progress(
    session: AsyncSession, token: DoctorQueue, now: datetime
) -> DoctorQueue:
    """Mark a queue entry as in_progress and set called_at timestamp."""
    await session.execute(
        update(DoctorQueue)
        .where(DoctorQueue.id == token.id)
        .values(status="in_progress", called_at=now)
    )
    token.status = "in_progress"
    token.called_at = now
    return token


async def recalculate_display_positions(
    session: AsyncSession,
    doctor_id: int,
    appointment_date: date,
    queue_session: str,
) -> None:
    """
    Recalculate display_position for all waiting tokens after a queue event.

    Called after: consult complete, emergency insertion, anchor trigger, delay reflow.
    display_position is 1-indexed and represents the patient's live position in queue.
    """
    # Fetch all waiting tokens in priority order
    waiting_result = await session.execute(
        select(DoctorQueue)
        .where(
            DoctorQueue.doctor_id == doctor_id,
            DoctorQueue.appointment_date == appointment_date,
            DoctorQueue.session == queue_session,
            DoctorQueue.status.in_(["waiting", "pending"]),
        )
        .order_by(
            # Emergency first
            (DoctorQueue.tier != "emergency"),
            # Then anchor slots
            (DoctorQueue.slot_type != "anchor"),
            # Then priority
            (DoctorQueue.tier != "priority"),
            # Then FCFS
            DoctorQueue.booked_at,
        )
    )
    waiting_tokens = waiting_result.scalars().all()

    for position, token in enumerate(waiting_tokens, start=1):
        await session.execute(
            update(DoctorQueue)
            .where(DoctorQueue.id == token.id)
            .values(display_position=position)
        )

    logger.debug(
        "Recalculated display_positions for %d waiting tokens — doctor_id=%s date=%s",
        len(waiting_tokens),
        doctor_id,
        appointment_date,
    )
