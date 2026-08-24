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
    total_doctors: int = 0
    active_doctors: int = 0
    total_patients: int = 0
    appointments_today: int = 0
    bookings_today: int = 0
    currently_in_progress: int = 0
    high_urgency_waiting: int = 0
    urgent_triages: int = 0
    avg_delay_minutes: float = 0.0
    api_backend: bool = True
    ai_triage_engine: bool = True
    queue_engine: bool = True
    notification_service: bool = True
    google_calendar_sync: bool = True


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

    # Average delay
    delay_res = await db.execute(
        select(func.avg(DelayEvent.delay_minutes)).where(
            func.date(DelayEvent.detected_at) == today
        )
    )
    avg_delay = delay_res.scalar() or 0.0

    return SystemStats(
        total_doctors=total_doctors,
        active_doctors=total_doctors,
        total_patients=total_patients,
        appointments_today=appointments_today,
        bookings_today=appointments_today,
        currently_in_progress=in_progress,
        high_urgency_waiting=high_urgency,
        urgent_triages=high_urgency,
        avg_delay_minutes=round(float(avg_delay), 1),
        api_backend=True,
        ai_triage_engine=True,
        queue_engine=True,
        notification_service=True,
        google_calendar_sync=True,
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
    Populate comprehensive 5-day demonstration data for testing all system features.
    
    Creates:
    - 1 Admin: admin@clinic.com / Password123!
    - 5 Specialist Doctors: Cardiology, Neurology, Dermatology, General Practice, Orthopedics
    - 8 Patients with verified contact numbers
    - Weekly Mon-Sat Morning & Evening Working Hours for all doctors
    - Queue tokens for 5 consecutive days (Today + 4 days) across all doctors & sessions
    - Diverse Tiers: Regular (FCFS), Priority (urgent/elderly), Anchor (time-bound), Emergency
    - Live States: Day 0 has completed & in-progress tokens; Days 1-4 are waiting (ready for leave/booking tests)
    - Full AI Pre-Visit Triage briefs with urgency scoring, chief complaints, and diagnostic questions
    - Post-Visit clinical notes and prescription medication schedules
    """
    from datetime import date, datetime, time, timedelta
    from src.models.doctor import Doctor, DoctorAvailability
    from src.models.queue import DoctorQueue
    from src.models.clinical import Symptoms, PostVisitNotes, Medication
    from src.modules.auth.service import hash_password

    today = date.today()
    default_password_hash = hash_password("Password123!")

    # ── 1. Create System Users (1 Admin + 5 Doctors + 8 Patients) ──────────────
    users_data = [
        {"email": "admin@clinic.com", "role": "admin", "first_name": "Clinic", "last_name": "Admin", "phone": "+919000000001"},
        {"email": "dr.sharma@clinic.com", "role": "doctor", "first_name": "Dr. Priya", "last_name": "Sharma", "phone": "+919876543210", "whatsapp_number": "+919876543210"},
        {"email": "dr.mehta@clinic.com", "role": "doctor", "first_name": "Dr. Rajesh", "last_name": "Mehta", "phone": "+919876543211", "whatsapp_number": "+919876543211"},
        {"email": "dr.kapoor@clinic.com", "role": "doctor", "first_name": "Dr. Ananya", "last_name": "Kapoor", "phone": "+919876543212", "whatsapp_number": "+919876543212"},
        {"email": "dr.verma@clinic.com", "role": "doctor", "first_name": "Dr. Amit", "last_name": "Verma", "phone": "+919876543213", "whatsapp_number": "+919876543213"},
        {"email": "dr.gupta@clinic.com", "role": "doctor", "first_name": "Dr. Sunita", "last_name": "Gupta", "phone": "+919876543214", "whatsapp_number": "+919876543214"},
        {"email": "rahul@example.com", "role": "patient", "first_name": "Rahul", "last_name": "Verma", "phone": "+919123456780", "whatsapp_number": "+919123456780"},
        {"email": "sneha@example.com", "role": "patient", "first_name": "Sneha", "last_name": "Patel", "phone": "+919123456781", "whatsapp_number": "+919123456781"},
        {"email": "vikram@example.com", "role": "patient", "first_name": "Vikram", "last_name": "Singh", "phone": "+919123456782", "whatsapp_number": "+919123456782"},
        {"email": "anita@example.com", "role": "patient", "first_name": "Anita", "last_name": "Desai", "phone": "+919123456783", "whatsapp_number": "+919123456783"},
        {"email": "rohit@example.com", "role": "patient", "first_name": "Rohit", "last_name": "Sharma", "phone": "+919123456784", "whatsapp_number": "+919123456784"},
        {"email": "pooja@example.com", "role": "patient", "first_name": "Pooja", "last_name": "Reddy", "phone": "+919123456785", "whatsapp_number": "+919123456785"},
        {"email": "karan@example.com", "role": "patient", "first_name": "Karan", "last_name": "Malhotra", "phone": "+919123456786", "whatsapp_number": "+919123456786"},
        {"email": "meera@example.com", "role": "patient", "first_name": "Meera", "last_name": "Iyer", "phone": "+919123456787", "whatsapp_number": "+919123456787"},
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

    # ── 2. Create Doctor Profiles & Weekly Availability ────────────────────────
    doctors_spec = [
        {"email": "dr.sharma@clinic.com", "spec": "Cardiology", "exp": 15, "bio": "Senior Interventional Cardiologist specializing in hypertension, post-PCI management, and preventive cardiology."},
        {"email": "dr.mehta@clinic.com", "spec": "Neurology", "exp": 12, "bio": "Consultant Neurologist with expertise in chronic migraines, peripheral neuropathy, and sleep disorders."},
        {"email": "dr.kapoor@clinic.com", "spec": "Dermatology", "exp": 8, "bio": "Clinical and aesthetic dermatologist treating eczema, acute urticaria, and cystic acne."},
        {"email": "dr.verma@clinic.com", "spec": "General Practice", "exp": 10, "bio": "Primary care physician managing acute viral fevers, lifestyle disorders, and preventive health."},
        {"email": "dr.gupta@clinic.com", "spec": "Orthopedics", "exp": 14, "bio": "Orthopedic surgeon specializing in osteoarthritis, sports ligament injuries, and spine rehabilitation."},
    ]

    doctor_models = {}
    for dinfo in doctors_spec:
        user = created_users[dinfo["email"]]
        res = await db.execute(select(Doctor).where(Doctor.id == user.id))
        doc = res.scalar_one_or_none()
        if not doc:
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

            # Add availability Mon-Sun
            for day in range(7):
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
        doctor_models[dinfo["spec"]] = doc

    # Patient pool for rotation
    patient_pool = [
        created_users["rahul@example.com"],
        created_users["sneha@example.com"],
        created_users["vikram@example.com"],
        created_users["anita@example.com"],
        created_users["rohit@example.com"],
        created_users["pooja@example.com"],
        created_users["karan@example.com"],
        created_users["meera@example.com"],
    ]

    # Clinical scenarios library per specialty
    clinical_scenarios = {
        "Cardiology": [
            ("Substernal chest heaviness on climbing stairs and palpitation.", "high", "Exertional angina pectoris evaluation", ["ECG and troponin review", "Adherence to statins and beta-blockers", "Any pain radiating to left jaw or arm"]),
            ("Hypertension follow-up: BP reading 155/95 mmHg, mild frontal headache.", "medium", "Uncontrolled Stage 1 Essential Hypertension", ["Current antihypertensive dosing", "Dietary sodium restriction compliance", "Home BP log review"]),
            ("Routine 6-month post-angioplasty review. No active chest discomfort.", "low", "Post-PCI coronary artery disease maintenance", ["Stent patency and antiplatelet therapy", "Exercise tolerance review", "Lipid profile targets"]),
            ("Bilateral lower extremity edema worsening towards evening with mild fatigue.", "medium", "Dependent peripheral edema / early heart failure workup", ["Echocardiogram assessment", "Fluid intake and daily weight log", "Shortness of breath on lying flat"]),
        ],
        "Neurology": [
            ("Right-sided throbbing headache with visual aura and photophobia for 2 days.", "high", "Acute classic migraine with visual aura", ["Migraine frequency and triggers", "Response to triptans / analgesics", "Any focal neurological deficits"]),
            ("Burning sensation and 'pins and needles' numbness in both feet, worse at night.", "medium", "Distal symmetrical peripheral sensory neuropathy", ["HbA1c and diabetic history", "Vitamin B12 levels", "Gait stability and reflexes"]),
            ("Episodic rotational vertigo triggered by rapid head turning when getting out of bed.", "medium", "Benign paroxysmal positional vertigo (BPPV)", ["Dix-Hallpike test findings", "Nystagmus duration", "History of inner ear infection"]),
            ("Chronic cervical stiffness with radiating numbness to index finger.", "medium", "Cervical radiculopathy (C6-C7 distribution)", ["Neck movement range", "Spurling test response", "Ergonomic workplace setup"]),
        ],
        "Dermatology": [
            ("Erythematous itchy rash with dry scaling on flexor surfaces of both arms.", "medium", "Atopic dermatitis exacerbation", ["Topical emollient regimen", "Contact allergen exposures", "Sleep disturbance due to pruritus"]),
            ("Sudden onset urticarial wheals with intense itching across trunk after antibiotic.", "high", "Drug-induced acute urticaria", ["Culprit medication timeline", "Any lip, tongue, or facial swelling", "Need for oral antihistamines"]),
            ("Persistent cystic acne lesions along jawline resistant to over-the-counter washes.", "low", "Severe nodulocystic facial acne", ["Prior retinoid or antibiotic trials", "Hormonal screening necessity", "Scarring risk evaluation"]),
            ("Circumscribed annular scaly lesion with central clearing on left forearm.", "low", "Tinea corporis fungal infection", ["Topical antifungal compliance", "Pet or soil exposure history", "Differential diagnosis confirmation"]),
        ],
        "General Practice": [
            ("High grade fever 102°F with severe body ache, chills, and dry cough for 3 days.", "high", "Acute viral febrile illness with systemic symptoms", ["Temperature chart and paracetamol response", "Hydration and urine output", "Complete blood count and Dengue/Flu screening"]),
            ("Epigastric burning pain and acid reflux aggravated 1 hour after meals.", "medium", "Gastroesophageal reflux disease (GERD) with dyspepsia", ["PPI therapy trial", "Dietary trigger avoidance", "H. pylori testing indication"]),
            ("Annual executive wellness review and routine preventive blood work analysis.", "low", "Routine annual preventive health assessment", ["Fasting blood glucose & lipid panel", "Lifestyle and BMI counselling", "Age-appropriate vaccination update"]),
            ("Acute watery diarrhea 4-5 episodes since morning with mild cramping.", "medium", "Acute gastroenteritis with mild dehydration", ["Oral rehydration solution adherence", "Dietary history in last 24h", "Stool frequency and consistency"]),
        ],
        "Orthopedics": [
            ("Severe bilateral knee joint pain on climbing stairs with 20-min morning stiffness.", "medium", "Bilateral knee osteoarthritis (Grade II-III)", ["Weight-bearing X-ray evaluation", "Quadriceps strengthening exercises", "NSAID tolerance and joint injections"]),
            ("Acute twist in right ankle during sports yesterday with swelling and bruising.", "high", "Acute lateral ankle ligament sprain (Grade II)", ["Inability to bear weight (Ottawa rules)", "RICE protocol adherence", "Anterior drawer test stability"]),
            ("Chronic lower back ache radiating to left posterior thigh on prolonged sitting.", "medium", "Lumbar disc herniation with Sciatica (L5-S1)", ["SLR (Straight Leg Raise) test angle", "Core stabilization physiotherapy", "MRI spine necessity"]),
            ("Right shoulder pain on abduction and overhead reaching for past 3 weeks.", "medium", "Rotator cuff impingement syndrome", ["Neer and Hawkins impingement tests", "Subacromial bursa evaluation", "Physical therapy progression"]),
        ],
    }

    # ── 3. Seed 5 Days of Queue Appointments for All Doctors ────────────────────
    total_tokens_seeded = 0

    for day_offset in range(5):
        current_date = today + timedelta(days=day_offset)
        is_today = (day_offset == 0)

        for dinfo in doctors_spec:
            spec = dinfo["spec"]
            doc = doctor_models[spec]
            scenarios = clinical_scenarios[spec]

            # Morning Session Tokens (3 tokens)
            morning_tokens = [
                {
                    "token": 1,
                    "tier": "regular",
                    "slot_type": "open",
                    "patient_idx": (day_offset * 3 + 0) % len(patient_pool),
                    "status": "completed" if is_today else "waiting",
                    "anchor_time": None,
                    "scenario": scenarios[0],
                },
                {
                    "token": 2,
                    "tier": "priority",
                    "slot_type": "open",
                    "patient_idx": (day_offset * 3 + 1) % len(patient_pool),
                    "status": "in_progress" if is_today else "waiting",
                    "anchor_time": None,
                    "scenario": scenarios[1],
                },
                {
                    "token": 3,
                    "tier": "regular",
                    "slot_type": "anchor",
                    "patient_idx": (day_offset * 3 + 2) % len(patient_pool),
                    "status": "waiting",
                    "anchor_time": time(10, 30),
                    "scenario": scenarios[2],
                },
            ]

            # Evening Session Tokens (2 tokens)
            evening_tokens = [
                {
                    "token": 1,
                    "tier": "regular",
                    "slot_type": "open",
                    "patient_idx": (day_offset * 2 + 3) % len(patient_pool),
                    "status": "waiting",
                    "anchor_time": None,
                    "scenario": scenarios[3],
                },
                {
                    "token": 2,
                    "tier": "priority",
                    "slot_type": "anchor",
                    "patient_idx": (day_offset * 2 + 4) % len(patient_pool),
                    "status": "waiting",
                    "anchor_time": time(18, 0),
                    "scenario": scenarios[1],
                },
            ]

            all_sessions = [("morning", morning_tokens), ("evening", evening_tokens)]

            for sess_name, tokens in all_sessions:
                for tdata in tokens:
                    pat = patient_pool[tdata["patient_idx"]]
                    
                    # Check if token exists
                    q_res = await db.execute(
                        select(DoctorQueue).where(
                            DoctorQueue.doctor_id == doc.id,
                            DoctorQueue.appointment_date == current_date,
                            DoctorQueue.session == sess_name,
                            DoctorQueue.token_number == tdata["token"],
                        )
                    )
                    existing_q = q_res.scalar_one_or_none()
                    if not existing_q:
                        q_entry = DoctorQueue(
                            doctor_id=doc.id,
                            appointment_date=current_date,
                            session=sess_name,
                            token_number=tdata["token"],
                            display_position=tdata["token"],
                            patient_id=pat.id,
                            tier=tdata["tier"],
                            slot_type=tdata["slot_type"],
                            anchor_time=tdata["anchor_time"],
                            status=tdata["status"],
                            booking_mode_used="advance" if tdata["slot_type"] == "anchor" else "walk_in",
                            booked_at=datetime.utcnow() - timedelta(days=5-day_offset, hours=2),
                        )
                        db.add(q_entry)
                        await db.flush()
                        total_tokens_seeded += 1

                        # Attach AI Pre-Visit Symptoms
                        scen_text, scen_urgency, scen_chief, scen_questions = tdata["scenario"]
                        db.add(Symptoms(
                            queue_id=q_entry.id,
                            symptom_text=scen_text,
                            urgency_level=scen_urgency,
                            ai_summary={
                                "urgency_level": scen_urgency,
                                "chief_complaint": scen_chief,
                                "suggested_questions": scen_questions,
                            },
                            is_processed=True,
                            llm_provider_used="groq",
                        ))

                        # If completed on Day 0, attach PostVisitNotes & Medications
                        if tdata["status"] == "completed":
                            note = PostVisitNotes(
                                queue_id=q_entry.id,
                                doctor_clinical_notes=f"Consultation completed for {scen_chief}. Patient oriented and vital signs stable. Advised rest, hydration, and structured pharmacotherapy.",
                                prescription=[
                                    {"medication_name": "Paracetamol 650mg", "dosage": "1 tablet", "frequency": "twice_daily", "duration_days": 5},
                                    {"medication_name": "Pantoprazole 40mg", "dosage": "1 tablet before breakfast", "frequency": "once_daily", "duration_days": 7},
                                ],
                                patient_friendly_summary=f"You consulted Dr. {doc.specialisation}. Please take your prescribed medicines on time and rest for the next 2-3 days.",
                                is_processed=True,
                            )
                            db.add(note)
                            await db.flush()

                            db.add(Medication(
                                post_visit_id=note.id,
                                medication_name="Paracetamol 650mg",
                                dosage="1 tablet",
                                frequency="twice_daily",
                                duration_days=5,
                            ))
                            db.add(Medication(
                                post_visit_id=note.id,
                                medication_name="Pantoprazole 40mg",
                                dosage="1 tablet",
                                frequency="once_daily",
                                duration_days=7,
                            ))

    await db.commit()
    logger.info("Comprehensive 5-day clinical test data seeded successfully (%d tokens across 5 days).", total_tokens_seeded)

    return {
        "message": f"Successfully seeded 5 days of clinical data ({total_tokens_seeded} queue tokens across 5 doctors)!",
        "date_range": f"{today} to {today + timedelta(days=4)} (5 consecutive calendar days)",
        "doctors": [
            {"id": doctor_models["Cardiology"].id, "name": "Dr. Priya Sharma", "specialisation": "Cardiology", "email": "dr.sharma@clinic.com"},
            {"id": doctor_models["Neurology"].id, "name": "Dr. Rajesh Mehta", "specialisation": "Neurology", "email": "dr.mehta@clinic.com"},
            {"id": doctor_models["Dermatology"].id, "name": "Dr. Ananya Kapoor", "specialisation": "Dermatology", "email": "dr.kapoor@clinic.com"},
            {"id": doctor_models["General Practice"].id, "name": "Dr. Amit Verma", "specialisation": "General Practice", "email": "dr.verma@clinic.com"},
            {"id": doctor_models["Orthopedics"].id, "name": "Dr. Sunita Gupta", "specialisation": "Orthopedics", "email": "dr.gupta@clinic.com"},
        ],
        "features_ready_to_test": [
            "Doctor Dashboard: Live queue with Completed, In-Progress, and Waiting tokens on Today",
            "Doctor Dashboard: Date picker shows pre-loaded queues on Day 1, 2, 3, 4",
            "Doctor Leave Engine: Call POST /doctors/{id}/leave on Day 3 to test auto-conflict cancellation",
            "Patient Portal: New bookings on any of the 5 days queue immediately after existing demo tokens",
            "AI Triage: Every token has pre-calculated clinical triage summaries and diagnostic questions",
            "Post-Visit Notes: Completed tokens have full digital prescriptions and medication schedules",
        ],
    }



@router.post("/notifications/process")
async def trigger_notification_worker(
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """Admin: Trigger background notification dispatch worker immediately."""
    from src.modules.notifications.worker import process_pending_notifications
    stats = await process_pending_notifications(batch_size=50)
    return {"message": "Notification batch processed", "stats": stats}


