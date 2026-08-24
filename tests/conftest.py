"""
pytest conftest — async database and test fixture setup.

Uses a real in-transaction async PostgreSQL test DB (not mocks).
Each test runs in a rolled-back transaction to preserve isolation.
"""

import asyncio
from datetime import date, time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.models.base import Base
from src.models.clinical import Medication, MedicationReminder, PostVisitNotes, Symptoms
from src.models.doctor import Doctor, DoctorAvailability
from src.models.integration import LLMCallLog, Notification
from src.models.queue import DelayEvent, DoctorQueue, UrgencyEscalationLog
from src.models.user import User
from src.modules.auth.service import hash_password

settings = get_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Override pytest-asyncio event loop to use session scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create tables once per test session, drop after."""
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncSession:
    """
    Provide a test session that rolls back after each test.

    This ensures complete isolation between tests without requiring
    database truncation or re-seeding between runs.
    """
    SessionFactory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with SessionFactory() as s:
        async with s.begin():
            yield s
            await s.rollback()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def patient_user(session: AsyncSession) -> User:
    """Create and return a test patient user."""
    user = User(
        email="patient@test.com",
        password_hash=hash_password("testpass123"),
        role="patient",
        first_name="Test",
        last_name="Patient",
        phone="+911234567890",
        whatsapp_number="+911234567890",
    )
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def doctor_user(session: AsyncSession) -> User:
    """Create and return a test doctor user."""
    user = User(
        email="doctor@test.com",
        password_hash=hash_password("testpass123"),
        role="doctor",
        first_name="Dr. Test",
        last_name="Doctor",
        phone="+919876543210",
    )
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def doctor(session: AsyncSession, doctor_user: User) -> Doctor:
    """Create and return a test doctor profile with morning availability."""
    doc = Doctor(
        id=doctor_user.id,
        specialisation="General Practice",
        bio="Test doctor for unit tests",
        experience_years=10,
        slot_duration_minutes=15,
        avg_consult_minutes=12.5,
        consult_sample_size=20,
        booking_mode="hybrid",
        anchor_slot_pct=25.00,
        priority_slot_pct=25.00,
        emergency_slot_pct=10.00,
    )
    session.add(doc)

    availability = DoctorAvailability(
        doctor_id=doctor_user.id,
        day_of_week=0,  # Monday
        session="morning",
        start_time=time(9, 0),
        end_time=time(13, 0),
        is_working_day=True,
    )
    session.add(availability)
    await session.flush()
    return doc


@pytest_asyncio.fixture
async def queue_entry(
    session: AsyncSession, doctor: Doctor, patient_user: User
) -> DoctorQueue:
    """Create a single waiting queue entry for the test doctor."""
    entry = DoctorQueue(
        doctor_id=doctor.id,
        appointment_date=date(2026, 9, 1),
        session="morning",
        token_number=1,
        display_position=1,
        patient_id=patient_user.id,
        tier="regular",
        slot_type="open",
        status="waiting",
        booking_mode_used="advance",
    )
    session.add(entry)
    await session.flush()
    return entry
