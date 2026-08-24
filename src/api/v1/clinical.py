"""
Clinical API router — symptom intake, pre-visit triage, and post-visit notes.

POST /clinical/{queue_id}/symptoms        — Patient submits symptoms before visit
GET  /clinical/{queue_id}/symptoms        — Doctor views AI triage summary
POST /clinical/{queue_id}/post-visit      — Doctor submits clinical notes + prescription
GET  /clinical/{queue_id}/post-visit      — Patient views post-visit summary
"""

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.logger import get_logger
from src.models.clinical import Medication, PostVisitNotes, Symptoms
from src.models.integration import LLMCallLog
from src.models.queue import DoctorQueue
from src.models.user import User
from src.modules.ai.router import llm_extract
from src.modules.auth.dependencies import get_current_user, require_role
from src.schemas.ai import PostVisitSummary, PreVisitTriage, UrgencyLevel

logger = get_logger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class SymptomSubmitRequest(BaseModel):
    symptom_text: str = Field(..., min_length=10, max_length=2000)


class SymptomResponse(BaseModel):
    queue_id: int
    symptom_text: str
    urgency_level: str | None
    chief_complaint: str | None
    suggested_questions: list[str]
    is_processed: bool
    ai_unavailable: bool = False


class PrescriptionItemRequest(BaseModel):
    medication_name: str | None = None
    name: str | None = None  # Frontend alias
    dosage: str | None = None
    frequency: str | None = None
    duration_days: int | None = None

    def get_name(self) -> str:
        return self.medication_name or self.name or "Medication"


class PostVisitRequest(BaseModel):
    doctor_clinical_notes: str | None = None
    raw_notes: str | None = None  # Frontend alias
    prescription: list[PrescriptionItemRequest] = Field(default_factory=list)
    medications: list[PrescriptionItemRequest] = Field(default_factory=list)  # Frontend alias

    def get_notes(self) -> str:
        return (self.doctor_clinical_notes or self.raw_notes or "").strip()

    def get_prescription(self) -> list[PrescriptionItemRequest]:
        items = self.prescription or self.medications or []
        # Ensure medication_name is set
        for item in items:
            if not item.medication_name and item.name:
                item.medication_name = item.name
        return items


class PostVisitResponse(BaseModel):
    queue_id: int
    patient_friendly_summary: str | None
    medication_schedule: str | None
    follow_up_steps: list[str]
    is_processed: bool
    ai_unavailable: bool = False


# ── Background LLM Tasks ──────────────────────────────────────────────────────


async def _run_pre_visit_triage(queue_id: int, symptom_text: str, symptom_id: int):
    """
    Background task: run LLM pre-visit triage and update symptoms table.

    NON-BLOCKING — runs after HTTP response is returned to client.
    If LLM fails: is_processed stays False, raw text preserved.
    """
    from src.core.database import _SessionFactory

    prompt = (
        f"You are an expert AI clinical assistant. Analyze these patient-reported symptoms "
        f"and provide a structured pre-visit triage summary.\n\n"
        f"Patient Symptoms:\n\"\"\"\n{symptom_text}\n\"\"\"\n\n"
        f"Urgency level must be: low, medium, high, or critical. "
        f"Provide the chief complaint and 2-4 suggested diagnostic questions."
    )

    result = await llm_extract(
        response_model=PreVisitTriage,
        prompt=prompt,
        call_type="pre_visit",
        queue_id=queue_id,
    )

    async with _SessionFactory() as session:
        async with session.begin():
            symptom_result = await session.execute(
                select(Symptoms).where(Symptoms.id == symptom_id)
            )
            symptom = symptom_result.scalar_one_or_none()
            if symptom is None:
                return

            if result is not None:
                symptom.urgency_level = result.urgency_level.value
                symptom.ai_summary = {
                    "urgency_level": result.urgency_level.value,
                    "chief_complaint": result.chief_complaint,
                    "suggested_questions": result.suggested_questions,
                }
                symptom.is_processed = True
                logger.info(
                    "Pre-visit triage complete — queue_id=%s urgency=%s",
                    queue_id, result.urgency_level,
                )
            else:
                # LLM failed — raw text already preserved, is_processed stays False
                symptom.urgency_level = UrgencyLevel.MEDIUM.value  # Conservative default
                logger.warning(
                    "Pre-visit triage LLM failed — queue_id=%s using default urgency=medium",
                    queue_id,
                )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/{queue_id}/symptoms", status_code=status.HTTP_201_CREATED)
async def submit_symptoms(
    queue_id: int,
    body: SymptomSubmitRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Patient submits pre-visit symptoms.

    1. Stores raw symptom_text immediately (always preserved).
    2. Triggers LLM triage asynchronously in background.
    3. Returns immediately — LLM processing is non-blocking.
    """
    # Verify queue entry ownership
    entry_result = await db.execute(select(DoctorQueue).where(DoctorQueue.id == queue_id))
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError(f"Queue entry {queue_id} not found")
    if entry.patient_id != current_user.id and current_user.role != "admin":
        raise ForbiddenError("You can only submit symptoms for your own appointment")

    # Check if symptoms already submitted — if so, update & re-triage instead of failing with 409
    existing = await db.execute(select(Symptoms).where(Symptoms.queue_id == queue_id))
    symptom = existing.scalar_one_or_none()
    if symptom:
        symptom.symptom_text = body.symptom_text
        symptom.is_processed = False
    else:
        symptom = Symptoms(
            queue_id=queue_id,
            symptom_text=body.symptom_text,
            is_processed=False,
        )
        db.add(symptom)

    await db.commit()
    await db.refresh(symptom)

    # Trigger LLM triage asynchronously — non-blocking
    background_tasks.add_task(
        _run_pre_visit_triage,
        queue_id=queue_id,
        symptom_text=body.symptom_text,
        symptom_id=symptom.id,
    )

    logger.info("Symptoms submitted — queue_id=%s patient_id=%s", queue_id, current_user.id)
    return {
        "message": "Symptoms recorded. AI triage is processing in the background.",
        "symptom_id": symptom.id,
        "queue_id": queue_id,
    }


@router.get("/{queue_id}/symptoms", response_model=SymptomResponse)
async def get_symptoms(
    queue_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> SymptomResponse:
    """Doctor or patient views symptom triage results."""
    symptom_result = await db.execute(select(Symptoms).where(Symptoms.queue_id == queue_id))
    symptom = symptom_result.scalar_one_or_none()
    if symptom is None:
        raise NotFoundError(f"No symptoms found for queue entry {queue_id}")

    ai_summary = symptom.ai_summary or {}
    return SymptomResponse(
        queue_id=queue_id,
        symptom_text=symptom.symptom_text,
        urgency_level=symptom.urgency_level,
        chief_complaint=ai_summary.get("chief_complaint"),
        suggested_questions=ai_summary.get("suggested_questions", []),
        is_processed=symptom.is_processed,
        ai_unavailable=not symptom.is_processed,
    )


@router.post("/{queue_id}/post-visit", status_code=status.HTTP_201_CREATED)
async def submit_post_visit(
    queue_id: int,
    body: PostVisitRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role("doctor")),
) -> dict:
    """
    Doctor submits post-visit clinical notes and prescription.

    1. Stores raw doctor_clinical_notes and prescription JSON immediately.
    2. Creates normalized Medication records from prescription items.
    3. Triggers LLM patient-summary generation asynchronously.
    4. Returns immediately — LLM processing is non-blocking.
    """
    entry_result = await db.execute(select(DoctorQueue).where(DoctorQueue.id == queue_id))
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError(f"Queue entry {queue_id} not found")
    if entry.doctor_id != current_user.id:
        raise ForbiddenError("You can only submit notes for your own patients")

    notes_text = body.get_notes()
    if not notes_text:
        from src.core.exceptions import ValidationError
        raise ValidationError("Clinical notes cannot be empty.")

    rx_items = body.get_prescription()
    prescription_json = [p.model_dump() for p in rx_items]

    # Check if notes already submitted — if so, update instead of 409
    existing = await db.execute(
        select(PostVisitNotes).where(PostVisitNotes.queue_id == queue_id)
    )
    note = existing.scalar_one_or_none()
    if note:
        note.doctor_clinical_notes = notes_text
        note.prescription = prescription_json
        note.is_processed = False
    else:
        note = PostVisitNotes(
            queue_id=queue_id,
            doctor_clinical_notes=notes_text,
            prescription=prescription_json,
            is_processed=False,
        )
        db.add(note)

    await db.flush()

    # Create or update normalized Medication records
    for item in rx_items:
        med = Medication(
            post_visit_id=note.id,
            medication_name=item.get_name(),
            dosage=item.dosage,
            frequency=item.frequency,
            duration_days=item.duration_days,
        )
        db.add(med)

    await db.commit()
    await db.refresh(note)

    # Trigger LLM summary asynchronously — non-blocking
    background_tasks.add_task(
        _run_post_visit_summary,
        queue_id=queue_id,
        note_id=note.id,
        clinical_notes=notes_text,
        prescription_json=prescription_json,
    )

    logger.info(
        "Post-visit notes submitted — queue_id=%s doctor_id=%s meds=%d",
        queue_id, current_user.id, len(body.prescription),
    )
    return {
        "message": "Post-visit notes saved. Patient summary is being generated.",
        "note_id": note.id,
        "queue_id": queue_id,
    }


async def _run_post_visit_summary(
    queue_id: int, note_id: int, clinical_notes: str, prescription_json: list
):
    """Background task: generate patient-friendly summary via LLM."""
    from src.core.database import _SessionFactory

    prompt = (
        f"You are a compassionate patient education specialist. "
        f"Translate these clinical notes into a patient-friendly summary.\n\n"
        f"Clinical Notes:\n\"\"\"\n{clinical_notes}\n\"\"\"\n\n"
        f"Prescription: {prescription_json}\n\n"
        f"Use simple language (6th-grade level). Include medication schedule and follow-up steps."
    )

    result = await llm_extract(
        response_model=PostVisitSummary,
        prompt=prompt,
        call_type="post_visit",
        queue_id=queue_id,
    )

    async with _SessionFactory() as session:
        async with session.begin():
            note_result = await session.execute(
                select(PostVisitNotes).where(PostVisitNotes.id == note_id)
            )
            note = note_result.scalar_one_or_none()
            if note and result is not None:
                note.patient_friendly_summary = result.patient_friendly_summary
                note.is_processed = True
                logger.info("Post-visit summary generated — queue_id=%s", queue_id)
            elif note:
                logger.warning(
                    "Post-visit LLM failed — queue_id=%s raw notes preserved", queue_id
                )


@router.get("/{queue_id}/post-visit", response_model=PostVisitResponse)
async def get_post_visit(
    queue_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> PostVisitResponse:
    """Patient or doctor views post-visit summary."""
    note_result = await db.execute(
        select(PostVisitNotes).where(PostVisitNotes.queue_id == queue_id)
    )
    note = note_result.scalar_one_or_none()
    if note is None:
        raise NotFoundError(f"No post-visit notes found for queue entry {queue_id}")

    return PostVisitResponse(
        queue_id=queue_id,
        patient_friendly_summary=note.patient_friendly_summary,
        medication_schedule=None,  # Populated from AI summary when available
        follow_up_steps=[],
        is_processed=note.is_processed,
        ai_unavailable=not note.is_processed,
    )
