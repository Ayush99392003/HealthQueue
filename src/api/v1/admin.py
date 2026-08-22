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
