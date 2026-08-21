"""Clinical models: symptoms, post-visit notes, medications, medication reminders."""

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Symptoms(Base, TimestampMixin):
    """
    Pre-visit symptom intake and AI triage result.

    is_processed=False means LLM failed — raw symptom_text is shown to the doctor.
    Raw text is always preserved regardless of LLM success/failure.
    """

    __tablename__ = "symptoms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), unique=True, nullable=False
    )
    symptom_text: Mapped[str] = mapped_column(Text, nullable=False)

    # AI extraction results — null if LLM failed
    ai_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    urgency_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    llm_provider_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)

    queue_entry: Mapped["DoctorQueue"] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="symptoms"
    )


class PostVisitNotes(Base, TimestampMixin):
    """
    Doctor post-visit clinical notes and AI-generated patient summary.

    is_processed=False means LLM failed — raw doctor_clinical_notes are shown to patient.
    prescription JSON is always stored as-is from the doctor's structured input.
    """

    __tablename__ = "post_visit_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), unique=True, nullable=False
    )
    doctor_clinical_notes: Mapped[str] = mapped_column(Text, nullable=False)
    prescription: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # AI-generated patient-friendly content — null if LLM failed
    patient_friendly_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)

    queue_entry: Mapped["DoctorQueue"] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="post_visit_notes"
    )
    medications: Mapped[list["Medication"]] = relationship(
        "Medication", back_populates="post_visit_note", cascade="all, delete-orphan"
    )


class Medication(Base, TimestampMixin):
    """Normalized prescription items extracted from post-visit JSONB prescription."""

    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_visit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("post_visit_notes.id"), nullable=False
    )
    medication_name: Mapped[str] = mapped_column(String(150), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # once_daily | twice_daily | thrice_daily | as_needed
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    post_visit_note: Mapped[PostVisitNotes] = relationship(
        "PostVisitNotes", back_populates="medications"
    )
    reminders: Mapped[list["MedicationReminder"]] = relationship(
        "MedicationReminder", back_populates="medication", cascade="all, delete-orphan"
    )


class MedicationReminder(Base, TimestampMixin):
    """Scheduled reminder jobs for medication adherence."""

    __tablename__ = "medication_reminders"
    __table_args__ = (
        Index("idx_med_reminders_due", "reminder_date", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    medication_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("medications.id"), nullable=False
    )
    queue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), nullable=False
    )
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)
    reminder_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|sent|failed
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    medication: Mapped[Medication] = relationship("Medication", back_populates="reminders")
    queue_entry: Mapped["DoctorQueue"] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="medication_reminders"
    )
