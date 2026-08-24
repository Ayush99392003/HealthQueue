"""Admin stats and scheduling dashboard router."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.logger import get_logger
from src.models.doctor import Doctor
from src.models.queue import DelayEvent, DoctorQueue
from src.models.user import User
from src.modules.auth.dependencies import require_role

logger = get_logger(__name__)
router = APIRouter()

from datetime import date


class SystemStats(BaseModel):
    total_doctors: int
    total_patients: int
    appointments_today: int
    currently_in_progress: int
    high_urgency_waiting: int


@router.get("/stats", response_model=SystemStats)
@router.get("/dashboard", response_model=SystemStats, include_in_schema=False)
async def get_stats(
    db: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> SystemStats:
    """Admin: System-wide KPI statistics."""
    today = date.today()

    total_doctors = (await db.execute(
        select(func.count(Doctor.id))
    )).scalar_one()

    total_patients = (await db.execute(
        select(func.count(User.id)).where(User.role == "patient")
    )).scalar_one()

    appointments_today = (await db.execute(
        select(func.count(DoctorQueue.id)).where(
            DoctorQueue.appointment_date == today,
            DoctorQueue.status.in_(["waiting", "in_progress", "completed"]),
        )
    )).scalar_one()

    in_progress = (await db.execute(
        select(func.count(DoctorQueue.id)).where(
            DoctorQueue.appointment_date == today,
            DoctorQueue.status == "in_progress",
        )
    )).scalar_one()

    high_urgency = (await db.execute(
        select(func.count(DoctorQueue.id)).where(
            DoctorQueue.appointment_date == today,
            DoctorQueue.tier == "emergency",
            DoctorQueue.status == "waiting",
        )
    )).scalar_one()

    return SystemStats(
        total_doctors=total_doctors,
        total_patients=total_patients,
        appointments_today=appointments_today,
        currently_in_progress=in_progress,
        high_urgency_waiting=high_urgency,
    )


@router.get("/scheduling-dashboard")
@router.get("/delays", include_in_schema=False)
async def scheduling_dashboard(
    db: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> list[dict]:
    """
    Admin: Live delay and utilization dashboard per doctor for today.

    Shows:
    - Live delay minutes per doctor
    - Tier utilization counts (regular/priority/emergency/anchor)
    - SLA breach flags (priority patient waiting > 30 min)
    """
    today = date.today()

    doctors_result = await db.execute(
        select(Doctor).join(User).where(User.is_active.is_(True))
    )
    doctors = doctors_result.scalars().all()

    dashboard = []
    for doctor in doctors:
        # Tier utilization
        queue_result = await db.execute(
            select(DoctorQueue).where(
                DoctorQueue.doctor_id == doctor.id,
                DoctorQueue.appointment_date == today,
                DoctorQueue.status.in_(["waiting", "in_progress", "completed"]),
            )
        )
        entries = queue_result.scalars().all()

        tier_counts = {"regular": 0, "priority": 0, "emergency": 0}
        slot_counts = {"open": 0, "anchor": 0}
        for e in entries:
            tier_counts[e.tier] = tier_counts.get(e.tier, 0) + 1
            slot_counts[e.slot_type] = slot_counts.get(e.slot_type, 0) + 1

        # Latest delay
        delay_result = await db.execute(
            select(DelayEvent).where(
                DelayEvent.doctor_id == doctor.id,
                DelayEvent.appointment_date == today,
            ).order_by(DelayEvent.detected_at.desc()).limit(1)
        )
        latest_delay = delay_result.scalar_one_or_none()

        dashboard.append({
            "doctor_id": doctor.id,
            "specialisation": doctor.specialisation,
            "delay_minutes": latest_delay.delay_minutes if latest_delay else 0,
            "tier_utilization": tier_counts,
            "slot_utilization": slot_counts,
            "waiting_emergency": tier_counts.get("emergency", 0),
            "total_today": len(entries),
        })

    return dashboard


@router.patch("/tier-config/{doctor_id}", status_code=200)
async def update_tier_config(
    doctor_id: int,
    anchor_slot_pct: float | None = None,
    priority_slot_pct: float | None = None,
    emergency_slot_pct: float | None = None,
    db: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """Admin: Update slot capacity split percentages for a doctor."""
    from src.core.exceptions import NotFoundError
    from sqlalchemy import update

    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise NotFoundError(f"Doctor {doctor_id} not found")

    updates = {}
    if anchor_slot_pct is not None:
        updates["anchor_slot_pct"] = anchor_slot_pct
    if priority_slot_pct is not None:
        updates["priority_slot_pct"] = priority_slot_pct
    if emergency_slot_pct is not None:
        updates["emergency_slot_pct"] = emergency_slot_pct

    if updates:
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(Doctor).where(Doctor.id == doctor_id).values(**updates)
        )
        await db.commit()
        logger.info("Tier config updated — doctor_id=%s updates=%s", doctor_id, updates)

    return {"message": "Tier configuration updated", "doctor_id": doctor_id, **updates}


@router.post("/seed-demo")
async def seed_demo_data(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Populate rich demonstration data for testing all system features.
    
    Creates:
    - 1 Admin: admin@clinic.com / Password123!
    - 5 Specialist Doctors: Cardiology, Neurology, Dermatology, General Practice, Orthopedics
    - Mon-Sat Morning & Evening Working Hours
    - 3 Test Patients: rahul@example.com, sneha@example.com, vikram@example.com
    - Queue tokens for today (Regular, Priority, Anchor, Emergency)
    - Pre-visit AI triage briefs and post-visit digital prescriptions
    """
    from datetime import date, datetime, time, timedelta
    from src.models.doctor import Doctor, DoctorAvailability
    from src.models.queue import DoctorQueue
    from src.models.clinical import Symptoms, PostVisitNotes, Medication
    from src.modules.auth.service import hash_password

    today = date.today()
    default_password_hash = hash_password("Password123!")

    # ── 1. Create System Users ────────────────────────────────────────────────
    users_data = [
        {"email": "admin@clinic.com", "role": "admin", "first_name": "Clinic", "last_name": "Admin", "phone": "+919000000001"},
        {"email": "dr.sharma@clinic.com", "role": "doctor", "first_name": "Dr. Priya", "last_name": "Sharma", "phone": "+919876543210"},
        {"email": "dr.mehta@clinic.com", "role": "doctor", "first_name": "Dr. Rajesh", "last_name": "Mehta", "phone": "+919876543211"},
        {"email": "dr.kapoor@clinic.com", "role": "doctor", "first_name": "Dr. Ananya", "last_name": "Kapoor", "phone": "+919876543212"},
        {"email": "dr.verma@clinic.com", "role": "doctor", "first_name": "Dr. Amit", "last_name": "Verma", "phone": "+919876543213"},
        {"email": "dr.gupta@clinic.com", "role": "doctor", "first_name": "Dr. Sunita", "last_name": "Gupta", "phone": "+919876543214"},
        {"email": "rahul@example.com", "role": "patient", "first_name": "Rahul", "last_name": "Verma", "phone": "+919123456780", "whatsapp_number": "+919123456780"},
        {"email": "sneha@example.com", "role": "patient", "first_name": "Sneha", "last_name": "Patel", "phone": "+919123456781", "whatsapp_number": "+919123456781"},
        {"email": "vikram@example.com", "role": "patient", "first_name": "Vikram", "last_name": "Singh", "phone": "+919123456782", "whatsapp_number": "+919123456782"},
    ]

    created_users = {}
    for udata in users_data:
        res = await db.execute(select(User).where(User.email == udata["email"]))
        existing = res.scalar_one_or_none()
        if existing:
            created_users[udata["email"]] = existing
        else:
            user = User(
                email=udata["email"],
                password_hash=default_password_hash,
                role=udata["role"],
                first_name=udata["first_name"],
                last_name=udata["last_name"],
                phone=udata.get("phone"),
                whatsapp_number=udata.get("whatsapp_number"),
            )
            db.add(user)
            await db.flush()
            created_users[udata["email"]] = user

    # ── 2. Create Doctor Profiles ─────────────────────────────────────────────
    doctors_spec = [
        {"email": "dr.sharma@clinic.com", "spec": "Cardiology", "exp": 15, "bio": "Senior Interventional Cardiologist specializing in hypertension and preventive cardiology."},
        {"email": "dr.mehta@clinic.com", "spec": "Neurology", "exp": 12, "bio": "Consultant Neurologist with expertise in chronic migraines, tremors, and sleep disorders."},
        {"email": "dr.kapoor@clinic.com", "spec": "Dermatology", "exp": 8, "bio": "Clinical and aesthetic dermatologist treating eczema, psoriasis, and acute rashes."},
        {"email": "dr.verma@clinic.com", "spec": "General Practice", "exp": 10, "bio": "Primary care physician managing acute infections, lifestyle disorders, and preventive health."},
        {"email": "dr.gupta@clinic.com", "spec": "Orthopedics", "exp": 14, "bio": "Orthopedic surgeon specializing in joint pain, sports injuries, and spine rehabilitation."},
    ]

    for dinfo in doctors_spec:
        user = created_users[dinfo["email"]]
        res = await db.execute(select(Doctor).where(Doctor.id == user.id))
        if not res.scalar_one_or_none():
            doc = Doctor(
                id=user.id,
                specialisation=dinfo["spec"],
                bio=dinfo["bio"],
                experience_years=dinfo["exp"],
                slot_duration_minutes=15,
                avg_consult_minutes=12.5,
                consult_sample_size=30,
                booking_mode="hybrid",
                anchor_slot_pct=25.0,
                priority_slot_pct=25.0,
                emergency_slot_pct=10.0,
            )
            db.add(doc)
            await db.flush()

            # Add availability Mon-Sat
            for day in range(6):
                db.add(DoctorAvailability(
                    doctor_id=user.id,
                    day_of_week=day,
                    session="morning",
                    start_time=time(9, 0),
                    end_time=time(13, 0),
                    is_working_day=True,
                ))
                db.add(DoctorAvailability(
                    doctor_id=user.id,
                    day_of_week=day,
                    session="evening",
                    start_time=time(17, 0),
                    end_time=time(20, 0),
                    is_working_day=True,
                ))

    # ── 3. Create Sample Today Queue Tokens for Dr. Sharma ────────────────────
    dr_sharma_id = created_users["dr.sharma@clinic.com"].id
    p_rahul = created_users["rahul@example.com"]
    p_sneha = created_users["sneha@example.com"]
    p_vikram = created_users["vikram@example.com"]

    sample_queue = [
        {
            "token": 1,
            "tier": "regular",
            "slot_type": "open",
            "patient": p_rahul,
            "status": "waiting",
            "booked_mins_ago": 45,
            "symptoms": "Severe throbbing headache for 3 days with nausea and sensitivity to light.",
            "urgency": "high",
            "chief_complaint": "Acute migraine attack with photophobia and nausea",
        },
        {
            "token": 2,
            "tier": "priority",
            "slot_type": "open",
            "patient": p_sneha,
            "status": "waiting",
            "booked_mins_ago": 30,
            "symptoms": "Age 68 follow-up: mild exertional dyspnea and swollen ankles in the evening.",
            "urgency": "medium",
            "chief_complaint": "Exertional shortness of breath with peripheral edema in elderly patient",
        },
        {
            "token": 3,
            "tier": "regular",
            "slot_type": "anchor",
            "anchor_time": time(10, 30),
            "patient": p_vikram,
            "status": "waiting",
            "booked_mins_ago": 60,
            "symptoms": "Routine 3-month post-angioplasty review. No active chest discomfort.",
            "urgency": "low",
            "chief_complaint": "Routine post-percutaneous coronary intervention follow-up",
        },
    ]

    for qitem in sample_queue:
        # Check if token exists for today
        q_res = await db.execute(
            select(DoctorQueue).where(
                DoctorQueue.doctor_id == dr_sharma_id,
                DoctorQueue.appointment_date == today,
                DoctorQueue.session == "morning",
                DoctorQueue.token_number == qitem["token"],
            )
        )
        existing_q = q_res.scalar_one_or_none()
        if not existing_q:
            q_entry = DoctorQueue(
                doctor_id=dr_sharma_id,
                appointment_date=today,
                session="morning",
                token_number=qitem["token"],
                display_position=qitem["token"],
                patient_id=qitem["patient"].id,
                tier=qitem["tier"],
                slot_type=qitem["slot_type"],
                anchor_time=qitem.get("anchor_time"),
                status=qitem["status"],
                booking_mode_used="advance",
                booked_at=datetime.utcnow() - timedelta(minutes=qitem["booked_mins_ago"]),
            )
            db.add(q_entry)
            await db.flush()

            # Pre-visit symptoms intake
            db.add(Symptoms(
                queue_id=q_entry.id,
                symptom_text=qitem["symptoms"],
                urgency_level=qitem["urgency"],
                ai_summary={
                    "urgency_level": qitem["urgency"],
                    "chief_complaint": qitem["chief_complaint"],
                    "suggested_questions": [
                        "When did the symptoms first manifest and has intensity changed?",
                        "Are you currently adhering to your baseline prescribed medications?",
                        "Have you observed any dizziness, chest discomfort, or visual disturbance?",
                    ],
                },
                is_processed=True,
                llm_provider_used="groq",
            ))

    await db.commit()
    logger.info("Demo clinical test data seeded successfully.")

    return {
        "message": "Demo data seeded successfully!",
        "admin_login": {"email": "admin@clinic.com", "password": "Password123!"},
        "doctor_logins": [
            {"name": "Dr. Priya Sharma", "specialisation": "Cardiology", "email": "dr.sharma@clinic.com", "password": "Password123!"},
            {"name": "Dr. Rajesh Mehta", "specialisation": "Neurology", "email": "dr.mehta@clinic.com", "password": "Password123!"},
            {"name": "Dr. Ananya Kapoor", "specialisation": "Dermatology", "email": "dr.kapoor@clinic.com", "password": "Password123!"},
            {"name": "Dr. Amit Verma", "specialisation": "General Practice", "email": "dr.verma@clinic.com", "password": "Password123!"},
            {"name": "Dr. Sunita Gupta", "specialisation": "Orthopedics", "email": "dr.gupta@clinic.com", "password": "Password123!"},
        ],
        "patient_logins": [
            {"name": "Rahul Verma", "email": "rahul@example.com", "password": "Password123!"},
            {"name": "Sneha Patel", "email": "sneha@example.com", "password": "Password123!"},
            {"name": "Vikram Singh", "email": "vikram@example.com", "password": "Password123!"},
        ],
        "active_queue": "3 pre-loaded tokens with AI Triage for Dr. Priya Sharma (Cardiology) for Today Morning Session",
    }

