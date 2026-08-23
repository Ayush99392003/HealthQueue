"""
Unit tests for the get_next_token() priority queue algorithm.

Tests verify the strict priority order:
Emergency → Anchor (within grace) → Priority (1-in-N) → Regular FCFS
"""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.queue import DoctorQueue
from src.modules.queue.engine import get_next_token

TEST_DATE = date(2026, 9, 1)
SESSION = "morning"


@pytest.mark.asyncio
async def test_emergency_served_before_regular(session: AsyncSession, doctor, patient_user):
    """Emergency tier patient must be served before any regular waiting patient."""
    regular = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=1, patient_id=patient_user.id, tier="regular",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 8, 0),  # booked first
    )
    emergency = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=2, patient_id=patient_user.id, tier="emergency",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 9, 30),  # booked later
    )
    session.add_all([regular, emergency])
    await session.flush()

    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    assert next_token is not None
    assert next_token.tier == "emergency"
    assert next_token.status == "in_progress"
    assert next_token.called_at is not None


@pytest.mark.asyncio
async def test_anchor_slot_served_when_time_arrived(session: AsyncSession, doctor, patient_user):
    """Anchor slot must be pulled forward when its anchor_time is in the past."""
    past_anchor_time = (datetime.utcnow() - timedelta(minutes=5)).time()

    anchor = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=1, patient_id=patient_user.id, tier="regular",
        slot_type="anchor", anchor_time=past_anchor_time, status="waiting",
        booking_mode_used="advance", booked_at=datetime(2026, 9, 1, 9, 0),
    )
    regular = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=2, patient_id=patient_user.id, tier="regular",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 8, 0),  # booked much earlier
    )
    session.add_all([anchor, regular])
    await session.flush()

    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    assert next_token is not None
    assert next_token.slot_type == "anchor"


@pytest.mark.asyncio
async def test_future_anchor_slot_not_served_early(session: AsyncSession, doctor, patient_user):
    """Anchor slot must NOT be served before its anchor_time (doctor running ahead)."""
    future_anchor_time = (datetime.utcnow() + timedelta(hours=2)).time()

    anchor = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=1, patient_id=patient_user.id, tier="regular",
        slot_type="anchor", anchor_time=future_anchor_time, status="waiting",
        booking_mode_used="advance", booked_at=datetime(2026, 9, 1, 9, 0),
    )
    regular = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=2, patient_id=patient_user.id, tier="regular",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 8, 0),
    )
    session.add_all([anchor, regular])
    await session.flush()

    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    # Should skip future anchor and serve regular FCFS instead
    assert next_token is not None
    assert next_token.slot_type == "open"
    assert next_token.tier == "regular"


@pytest.mark.asyncio
async def test_empty_queue_returns_none(session: AsyncSession, doctor):
    """Queue with no waiting patients must return None."""
    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)
    assert next_token is None


@pytest.mark.asyncio
async def test_regular_fcfs_ordering(session: AsyncSession, doctor, patient_user):
    """Regular open queue must serve in FCFS order (earliest booked_at first)."""
    late_token = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=2, patient_id=patient_user.id, tier="regular",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 9, 30),
    )
    early_token = DoctorQueue(
        doctor_id=doctor.id, appointment_date=TEST_DATE, session=SESSION,
        token_number=1, patient_id=patient_user.id, tier="regular",
        slot_type="open", status="waiting", booking_mode_used="advance",
        booked_at=datetime(2026, 9, 1, 8, 0),
    )
    session.add_all([late_token, early_token])
    await session.flush()

    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    assert next_token is not None
    assert next_token.token_number == 1  # earliest booked
