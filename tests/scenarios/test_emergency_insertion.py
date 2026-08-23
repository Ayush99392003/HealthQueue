"""
Scenario test: Emergency tier insertion into a live queue.

Verifies the full clinical emergency flow:
1. Several regular patients are already waiting.
2. An emergency patient is added mid-queue.
3. get_next_token() always returns the emergency patient next,
   regardless of when they booked or their token_number.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.queue import DoctorQueue
from src.modules.queue.engine import get_next_token, recalculate_display_positions

TEST_DATE = date(2026, 9, 2)
SESSION = "morning"


@pytest.mark.asyncio
async def test_emergency_inserted_served_immediately(session: AsyncSession, doctor, patient_user):
    """
    Scenario:
    - 5 regular patients are waiting (booked earlier)
    - 1 emergency patient walks in
    - get_next_token must serve emergency first
    """
    # Create 5 regular patients booked earlier
    regular_entries = []
    for i in range(5):
        entry = DoctorQueue(
            doctor_id=doctor.id,
            appointment_date=TEST_DATE,
            session=SESSION,
            token_number=i + 1,
            patient_id=patient_user.id,
            tier="regular",
            slot_type="open",
            status="waiting",
            booking_mode_used="advance",
            booked_at=datetime(2026, 9, 2, 8, 0) + timedelta(minutes=i * 5),
        )
        session.add(entry)
        regular_entries.append(entry)

    await session.flush()

    # Emergency patient arrives last (highest token_number)
    emergency = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=TEST_DATE,
        session=SESSION,
        token_number=6,
        patient_id=patient_user.id,
        tier="emergency",
        slot_type="open",
        status="waiting",
        booking_mode_used="walk_in",
        booked_at=datetime(2026, 9, 2, 9, 30),  # arrived last
    )
    session.add(emergency)
    await session.flush()

    # Recalculate positions
    await recalculate_display_positions(session, doctor.id, TEST_DATE, SESSION)

    # get_next_token must always pick emergency first
    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    assert next_token is not None
    assert next_token.tier == "emergency"
    assert next_token.token_number == 6  # Despite being last booked


@pytest.mark.asyncio
async def test_multiple_emergencies_served_in_fcfs_order(
    session: AsyncSession, doctor, patient_user
):
    """
    When multiple emergency patients are waiting,
    they must be served in FCFS order (earliest booked_at first).
    """
    emergency_1 = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=TEST_DATE,
        session=SESSION,
        token_number=1,
        patient_id=patient_user.id,
        tier="emergency",
        slot_type="open",
        status="waiting",
        booking_mode_used="walk_in",
        booked_at=datetime(2026, 9, 2, 9, 0),
    )
    emergency_2 = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=TEST_DATE,
        session=SESSION,
        token_number=2,
        patient_id=patient_user.id,
        tier="emergency",
        slot_type="open",
        status="waiting",
        booking_mode_used="walk_in",
        booked_at=datetime(2026, 9, 2, 9, 30),  # arrived later
    )
    session.add_all([emergency_2, emergency_1])  # Add in reverse to test ordering
    await session.flush()

    next_token = await get_next_token(session, doctor.id, TEST_DATE, SESSION)

    assert next_token is not None
    assert next_token.tier == "emergency"
    assert next_token.token_number == 1  # First emergency booked should be served first


@pytest.mark.asyncio
async def test_display_positions_recalculated_after_emergency(
    session: AsyncSession, doctor, patient_user
):
    """
    After emergency insertion, display_positions for regular patients
    must shift down (they move further back in queue).
    """
    regular = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=TEST_DATE,
        session=SESSION,
        token_number=1,
        patient_id=patient_user.id,
        tier="regular",
        slot_type="open",
        status="waiting",
        booking_mode_used="advance",
        booked_at=datetime(2026, 9, 2, 8, 0),
    )
    session.add(regular)
    await session.flush()

    # Initial position = 1
    await recalculate_display_positions(session, doctor.id, TEST_DATE, SESSION)
    await session.refresh(regular)
    assert regular.display_position == 1

    # Emergency patient joins
    emergency = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=TEST_DATE,
        session=SESSION,
        token_number=2,
        patient_id=patient_user.id,
        tier="emergency",
        slot_type="open",
        status="waiting",
        booking_mode_used="walk_in",
        booked_at=datetime(2026, 9, 2, 9, 0),
    )
    session.add(emergency)
    await session.flush()

    # After recalculation, emergency is position 1, regular is pushed to 2
    await recalculate_display_positions(session, doctor.id, TEST_DATE, SESSION)
    await session.refresh(regular)
    await session.refresh(emergency)

    assert emergency.display_position == 1
    assert regular.display_position == 2
