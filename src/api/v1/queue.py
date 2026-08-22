"""
Queue API router — booking, advance, and live status endpoints.

POST /queue/book       — Book a token (SERIALIZABLE transaction)
POST /queue/{id}/next  — Doctor advances queue (Complete & Call Next)
GET  /queue/{id}/status — Patient polls live status every 15-30s
"""

from datetime import date

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, NotFoundError
from src.core.logger import get_logger
from src.models.queue import DoctorQueue
from src.models.user import User
from src.modules.auth.dependencies import get_current_user, require_role
from src.modules.queue.engine import get_next_token, recalculate_display_positions
from src.modules.queue.eta import calculate_eta
from src.modules.queue.service import book_token

logger = get_logger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class BookingRequest(BaseModel):
    doctor_id: int
    appointment_date: date
    session: str = Field(..., description="morning | evening | full_day")
    tier: str = Field(default="regular", description="regular | priority | emergency")
    slot_type: str = Field(default="open", description="open | anchor")
    anchor_time: str | None = Field(default=None, description="HH:MM — required if slot_type=anchor")
    symptom_text: str | None = Field(default=None, max_length=2000)


class BookingResponse(BaseModel):
    queue_id: int
    token_number: int
    display_position: int | None
    tier: str
    slot_type: str
    anchor_time: str | None
    estimated_wait_minutes: int | None
    eta_time: str | None


class QueueStatusResponse(BaseModel):
    queue_id: int
    token_number: int
    status: str
    display_position: int | None
    patients_ahead: int | None
    estimated_wait_minutes: int | None
    eta_time: str | None
    current_delay_minutes: int
    tier: str


class NextTokenResponse(BaseModel):
    message: str
    next_queue_id: int | None
    next_token_number: int | None
    next_patient_name: str | None
    tier: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/book", status_code=status.HTTP_201_CREATED, response_model=BookingResponse)
async def book_appointment(
    body: BookingRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> BookingResponse:
    """
    Book a token in the queue.

    Runs inside a SERIALIZABLE transaction with SELECT ... FOR UPDATE.
    Retries up to 3 times on concurrency collisions.
    Returns 409 Conflict if all retries are exhausted.
    """
    if body.slot_type == "anchor" and not body.anchor_time:
        from src.core.exceptions import ValidationError
        raise ValidationError("anchor_time is required when slot_type='anchor'")

    entry = await book_token(
        doctor_id=body.doctor_id,
        appointment_date=body.appointment_date,
        queue_session=body.session,
        patient_id=current_user.id,
        tier=body.tier,
        slot_type=body.slot_type,
        anchor_time=body.anchor_time,
        booking_mode_used="advance" if body.slot_type == "anchor" else "walk_in",
    )

    # Fetch ETA for response
    eta_data = await calculate_eta(
        db,
        doctor_id=body.doctor_id,
        appointment_date=body.appointment_date,
        queue_session=body.session,
        patient_queue_id=entry.id,
    )

    # Store symptom text if provided (async LLM triage triggered separately)
    if body.symptom_text:
        from src.models.clinical import Symptoms
        symptom = Symptoms(
            queue_id=entry.id,
            symptom_text=body.symptom_text,
            is_processed=False,  # LLM triage runs asynchronously
        )
        db.add(symptom)
        await db.commit()

    logger.info(
        "Booking confirmed — queue_id=%s token=%d patient_id=%s",
        entry.id, entry.token_number, current_user.id,
    )
    return BookingResponse(
        queue_id=entry.id,
        token_number=entry.token_number,
        display_position=entry.display_position,
        tier=entry.tier,
        slot_type=entry.slot_type,
        anchor_time=str(entry.anchor_time) if entry.anchor_time else None,
        estimated_wait_minutes=eta_data["estimated_wait_minutes"],
        eta_time=eta_data["eta_time"],
    )


@router.get("/{queue_id}/status", response_model=QueueStatusResponse)
async def get_queue_status(
    queue_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> QueueStatusResponse:
    """
    Live queue status for a patient — polled every 15-30 seconds.

    Returns display_position, patients_ahead, ETA, and current delay.
    """
    result = await db.execute(select(DoctorQueue).where(DoctorQueue.id == queue_id))
    entry = result.scalar_one_or_none()

    if entry is None:
        raise NotFoundError(f"Queue entry {queue_id} not found")

    # Patients can only view their own queue entries
    if current_user.role == "patient" and entry.patient_id != current_user.id:
        raise ForbiddenError("You can only view your own queue status")

    eta_data = await calculate_eta(
        db,
        doctor_id=entry.doctor_id,
        appointment_date=entry.appointment_date,
        queue_session=entry.session,
        patient_queue_id=queue_id,
    )

    return QueueStatusResponse(
        queue_id=entry.id,
        token_number=entry.token_number,
        status=entry.status,
        display_position=eta_data["display_position"],
        patients_ahead=eta_data["patients_ahead"],
        estimated_wait_minutes=eta_data["estimated_wait_minutes"],
        eta_time=eta_data["eta_time"],
        current_delay_minutes=eta_data["current_delay_minutes"],
        tier=entry.tier,
    )


@router.post("/{queue_id}/complete", response_model=NextTokenResponse)
async def complete_and_call_next(
    queue_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role("doctor")),
) -> NextTokenResponse:
    """
    Doctor: Mark current consultation complete and call the next patient.

    Triggers:
    1. Mark current entry as 'completed' with completed_at timestamp.
    2. Run get_next_token() priority algorithm.
    3. Recalculate all display_positions for remaining patients.
    4. Run delay detection (async background — see delay/detector.py).
    """
    # Verify this queue entry belongs to the calling doctor
    result = await db.execute(select(DoctorQueue).where(DoctorQueue.id == queue_id))
    entry = result.scalar_one_or_none()

    if entry is None:
        raise NotFoundError(f"Queue entry {queue_id} not found")
    if entry.doctor_id != current_user.id:
        raise ForbiddenError("You can only advance your own queue")

    from datetime import datetime
    now = datetime.utcnow()

    async with db.begin():
        # Complete current consultation
        await db.execute(
            update(DoctorQueue)
            .where(DoctorQueue.id == queue_id)
            .values(status="completed", completed_at=now)
        )

        # Call next patient using priority algorithm
        next_entry = await get_next_token(
            db,
            doctor_id=entry.doctor_id,
            appointment_date=entry.appointment_date,
            queue_session=entry.session,
        )

        # Recalculate display_positions for remaining queue
        await recalculate_display_positions(
            db,
            doctor_id=entry.doctor_id,
            appointment_date=entry.appointment_date,
            queue_session=entry.session,
        )

    logger.info(
        "Consultation completed — queue_id=%s next_queue_id=%s",
        queue_id, next_entry.id if next_entry else None,
    )

    if next_entry is None:
        return NextTokenResponse(
            message="Queue is now empty — no more patients waiting",
            next_queue_id=None,
            next_token_number=None,
            next_patient_name=None,
            tier=None,
        )

    # Fetch next patient name for dashboard display
    patient_result = await db.execute(
        select(User).where(User.id == next_entry.patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"

    return NextTokenResponse(
        message="Next patient called",
        next_queue_id=next_entry.id,
        next_token_number=next_entry.token_number,
        next_patient_name=patient_name,
        tier=next_entry.tier,
    )
