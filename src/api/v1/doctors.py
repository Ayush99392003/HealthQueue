"""Doctor management API router."""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.logger import get_logger
from src.models.user import User
from src.modules.auth.dependencies import require_role
from src.modules.doctors import leave_conflict
from src.modules.doctors import service as doctor_service

logger = get_logger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class DoctorCreateRequest(BaseModel):
    user_id: int
    specialisation: str
    bio: str | None = None
    experience_years: int | None = None
    slot_duration_minutes: int = Field(default=15, gt=0)
    booking_mode: str = "hybrid"
    anchor_slot_pct: float = Field(default=25.0, ge=0, le=100)
    priority_slot_pct: float = Field(default=25.0, ge=0, le=100)
    emergency_slot_pct: float = Field(default=10.0, ge=0, le=100)


class AvailabilityRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    session: str = Field(..., description="morning | evening | full_day")
    start_time: str = Field(..., description="HH:MM format")
    end_time: str = Field(..., description="HH:MM format")
    is_working_day: bool = True


class LeaveRequest(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = None


class DoctorResponse(BaseModel):
    id: int
    specialisation: str
    bio: str | None
    experience_years: int | None
    slot_duration_minutes: int
    booking_mode: str
    anchor_slot_pct: float
    priority_slot_pct: float
    emergency_slot_pct: float
    is_available: bool

    model_config = {"from_attributes": True}


class LeaveConflictResponse(BaseModel):
    leave_id: int
    cancelled_count: int
    notifications_queued: int


class DoctorSuggestResponse(BaseModel):
    recommended_specialisation: str
    reason: str
    doctors: list[DoctorResponse]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/suggest", response_model=DoctorSuggestResponse)
async def suggest_doctors(
    symptoms: str = Query(..., description="Patient symptoms or diagnosis description"),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorSuggestResponse:
    """
    AI-powered doctor recommendation based on symptoms or diagnosis.

    Uses the LLM to extract the best-matching medical specialisation from
    the patient's symptoms/diagnosis, then returns available doctors.
    """
    from pydantic import Field as PydanticField
    from src.modules.ai.router import llm_extract

    class SpecialisationSuggest(BaseModel):
        specialisation: str = PydanticField(
            description=(
                "The single most appropriate medical specialisation for these symptoms. "
                "Use standard terms: Cardiology, Neurology, Orthopedics, ENT, Dermatology, "
                "General Practice, Pulmonology, Gastroenterology, Psychiatry, Ophthalmology, "
                "Obstetrics & Gynecology, Pediatrics, Urology, Endocrinology, Nephrology."
            )
        )
        reason: str = PydanticField(
            description="One-sentence clinical reasoning for this specialisation recommendation."
        )

    prompt = (
        f"You are a clinical triage AI. A patient describes their condition as:\n\n"
        f"\"{symptoms}\"\n\n"
        f"Determine the single most appropriate medical specialisation this patient should see "
        f"and provide a brief clinical reason."
    )

    result = await llm_extract(
        response_model=SpecialisationSuggest,
        prompt=prompt,
        call_type="doctor_suggest",
    )

    if result:
        recommended = result.specialisation
        reason = result.reason
    else:
        # LLM fallback — default to General Practice
        recommended = "General Practice"
        reason = "Unable to determine specialisation from symptoms. Defaulting to General Practice."

    doctors = await doctor_service.list_doctors(
        session,
        specialisation=recommended,
    )

    # If no exact match, return all doctors
    if not doctors:
        doctors = await doctor_service.list_doctors(session)
        reason += " No exact specialisation match found — showing all available doctors."

    return DoctorSuggestResponse(
        recommended_specialisation=recommended,
        reason=reason,
        doctors=[DoctorResponse.model_validate(d) for d in doctors],
    )



@router.post("", status_code=status.HTTP_201_CREATED, response_model=DoctorResponse)
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=DoctorResponse, include_in_schema=False)
async def create_doctor(
    body: DoctorCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> DoctorResponse:
    """Admin: Create a doctor profile for an existing doctor-role user."""
    async with session.begin():
        doctor = await doctor_service.create_doctor_profile(
            session,
            body.user_id,
            specialisation=body.specialisation,
            bio=body.bio,
            experience_years=body.experience_years,
            slot_duration_minutes=body.slot_duration_minutes,
            booking_mode=body.booking_mode,
            anchor_slot_pct=body.anchor_slot_pct,
            priority_slot_pct=body.priority_slot_pct,
            emergency_slot_pct=body.emergency_slot_pct,
        )
    return DoctorResponse.model_validate(doctor)


@router.get("", response_model=list[DoctorResponse])
@router.get("/", response_model=list[DoctorResponse], include_in_schema=False)
async def list_doctors(
    specialisation: str | None = None,
    booking_mode: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[DoctorResponse]:
    """List all active doctors with optional filters."""
    doctors = await doctor_service.list_doctors(
        session,
        specialisation=specialisation,
        booking_mode=booking_mode,
    )
    return [DoctorResponse.model_validate(d) for d in doctors]


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> DoctorResponse:
    """Get a doctor's public profile."""
    doctor = await doctor_service.get_doctor(session, doctor_id)
    return DoctorResponse.model_validate(doctor)


@router.post("/{doctor_id}/availability", status_code=status.HTTP_200_OK)
async def set_availability(
    doctor_id: int,
    body: AvailabilityRequest,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """Admin: Set or update a doctor's availability for a specific day and session."""
    async with session.begin():
        availability = await doctor_service.set_availability(
            session,
            doctor_id,
            day_of_week=body.day_of_week,
            session_name=body.session,
            start_time=body.start_time,
            end_time=body.end_time,
            is_working_day=body.is_working_day,
        )
    return {"message": "Availability updated", "availability_id": availability.id}


@router.post("/{doctor_id}/leave", status_code=status.HTTP_201_CREATED)
async def add_leave(
    doctor_id: int,
    body: LeaveRequest,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """
    Admin: Mark a doctor on leave and auto-cancel all conflicting appointments.

    After cancellation, leave_cancellation notifications are queued for every
    affected patient (WhatsApp primary, Email as formal record).
    """
    async with session.begin():
        leave_record = await doctor_service.add_leave(
            session,
            doctor_id,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
        )

        # Resolve conflicts — cancel appointments and queue notifications
        cancelled = await leave_conflict.resolve_leave_conflicts(
            session,
            doctor_id=doctor_id,
            start_date=body.start_date,
            end_date=body.end_date,
        )

    logger.info(
        "Leave created — doctor_id=%s leave_id=%s cancelled=%d",
        doctor_id, leave_record.id, len(cancelled),
    )
    return {
        "message": "Leave created and conflicting appointments cancelled",
        "leave_id": leave_record.id,
        "cancelled_appointments": len(cancelled),
        "notifications_queued": len(cancelled) * 2,  # WhatsApp + Email per patient
    }
