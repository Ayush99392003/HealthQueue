"""
Unit tests for the doctor leave conflict resolution engine.
"""

from datetime import date
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.doctor import Doctor
from src.models.queue import DoctorQueue
from src.models.user import User
from src.modules.doctors.leave_conflict import resolve_leave_conflicts


@pytest.mark.asyncio
async def test_resolve_leave_conflicts_cancels_matching_entries(
    session: AsyncSession, doctor: Doctor, patient_user: User
):
    """Leave conflict engine must cancel all waiting appointments within the leave range."""
    # 1. Create appointment within leave range
    appt_in_range = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=date(2026, 9, 10),
        session="morning",
        token_number=1,
        display_position=1,
        patient_id=patient_user.id,
        tier="regular",
        slot_type="open",
        status="waiting",
    )
    # 2. Create appointment outside leave range
    appt_out_of_range = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=date(2026, 9, 20),
        session="morning",
        token_number=1,
        display_position=1,
        patient_id=patient_user.id,
        tier="regular",
        slot_type="open",
        status="waiting",
    )
    session.add(appt_in_range)
    session.add(appt_out_of_range)
    await session.flush()

    # Apply leave from Sept 9 to Sept 12
    cancelled = await resolve_leave_conflicts(
        session,
        doctor_id=doctor.id,
        start_date=date(2026, 9, 9),
        end_date=date(2026, 9, 12),
    )

    assert len(cancelled) == 1
    assert cancelled[0].id == appt_in_range.id

    # Verify status in database
    res_in = await session.execute(select(DoctorQueue).where(DoctorQueue.id == appt_in_range.id))
    entry_in = res_in.scalar_one()
    assert entry_in.status == "cancelled"

    res_out = await session.execute(select(DoctorQueue).where(DoctorQueue.id == appt_out_of_range.id))
    entry_out = res_out.scalar_one()
    assert entry_out.status == "waiting"
