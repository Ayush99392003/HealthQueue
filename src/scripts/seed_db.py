"""
Database seeder — creates test doctor, patient, and admin accounts.

Run: uv run python -m src.scripts.seed_db

⚠️ ONLY for development/staging environments.
⚠️ Will fail on PRODUCTION (guarded by environment check).
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.logger import configure_logging, get_logger
from src.models.base import Base
from src.models.clinical import Medication, MedicationReminder, PostVisitNotes, Symptoms
from src.models.doctor import Doctor, DoctorAvailability, DoctorLeave
from src.models.integration import CalendarEvent, LLMCallLog, Notification, OAuthToken
from src.models.queue import DelayEvent, DoctorQueue, UrgencyEscalationLog
from src.models.user import User
from src.modules.auth.service import hash_password

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


async def seed():
    if settings.environment == "production":
        logger.error("Seed script must NOT be run in production")
        sys.exit(1)

    logger.info("Starting database seed for environment: %s", settings.environment)

    engine = create_async_engine(str(settings.database_url), echo=False)
    SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        # Create all tables (idempotent)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created/verified")

    async with SessionFactory() as session:
        async with session.begin():
            # ── Admin User ─────────────────────────────────────────
            admin = User(
                email="admin@clinic.com",
                password_hash=hash_password("Admin@1234"),
                role="admin",
                first_name="System",
                last_name="Admin",
                phone="+910000000001",
            )
            session.add(admin)
            await session.flush()
            logger.info("Admin user created — id=%s email=%s", admin.id, admin.email)

            # ── Doctor User + Profile ──────────────────────────────
            doctor_user = User(
                email="dr.sharma@clinic.com",
                password_hash=hash_password("Doctor@1234"),
                role="doctor",
                first_name="Dr. Priya",
                last_name="Sharma",
                phone="+919876543210",
                whatsapp_number="+919876543210",
            )
            session.add(doctor_user)
            await session.flush()

            doctor = Doctor(
                id=doctor_user.id,
                specialisation="General Medicine",
                bio="15+ years experience in internal medicine and primary care.",
                experience_years=15,
                slot_duration_minutes=15,
                avg_consult_minutes=12.5,
                consult_sample_size=50,
                booking_mode="hybrid",
                anchor_slot_pct=25.0,
                priority_slot_pct=25.0,
                emergency_slot_pct=10.0,
            )
            session.add(doctor)

            # Weekly availability: Mon-Sat Morning + Evening
            from datetime import time
            for day in range(6):  # Monday to Saturday
                for sess, start, end in [
                    ("morning", time(9, 0), time(13, 0)),
                    ("evening", time(17, 0), time(20, 0)),
                ]:
                    session.add(DoctorAvailability(
                        doctor_id=doctor_user.id,
                        day_of_week=day,
                        session=sess,
                        start_time=start,
                        end_time=end,
                        is_working_day=True,
                    ))

            logger.info("Doctor profile + availability created — id=%s", doctor_user.id)

            # ── Patient User ───────────────────────────────────────
            patient = User(
                email="patient@example.com",
                password_hash=hash_password("Patient@1234"),
                role="patient",
                first_name="Rahul",
                last_name="Verma",
                phone="+911234567890",
                whatsapp_number="+911234567890",
            )
            session.add(patient)
            await session.flush()
            logger.info("Patient user created — id=%s email=%s", patient.id, patient.email)

    logger.info("✅ Seed complete. Test credentials:")
    logger.info("  Admin:   admin@clinic.com / Admin@1234")
    logger.info("  Doctor:  dr.sharma@clinic.com / Doctor@1234")
    logger.info("  Patient: patient@example.com / Patient@1234")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
