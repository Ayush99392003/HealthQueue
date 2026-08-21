"""
Queue, urgency escalation log, and delay event models.

CRITICAL INVARIANTS (see AGENTS.md):
- token_number: immutable identifier assigned at booking — NEVER used for serving order.
- display_position: dynamic live serving order — recalculated by get_next_token() only.
"""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class DoctorQueue(Base, TimestampMixin):
    """
    Core token queue table.

    Invariants:
    - token_number is assigned atomically under SERIALIZABLE + FOR UPDATE.
    - display_position is set to None and recalculated by get_next_token() after every event.
    - status transitions: pending → waiting → in_progress → completed | cancelled | deferred
    """

    __tablename__ = "doctor_queue"
    __table_args__ = (
        UniqueConstraint(
            "doctor_id", "appointment_date", "session", "token_number",
            name="uq_doctor_date_session_token",
        ),
        Index("idx_queue_doctor_date_status", "doctor_id", "appointment_date", "session", "status"),
        Index("idx_queue_patient", "patient_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=False
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    session: Mapped[str] = mapped_column(String(10), nullable=False)

    # Identification — immutable after booking
    token_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Live serving order — recalculated dynamically, never infer from token_number
    display_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    tier: Mapped[str] = mapped_column(String(10), nullable=False, default="regular")
    slot_type: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    anchor_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    status: Mapped[str] = mapped_column(String(15), nullable=False, default="waiting")
    booking_mode_used: Mapped[str | None] = mapped_column(String(15))

    deferred_from_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), nullable=True
    )

    booked_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    doctor: Mapped["Doctor"] = relationship(  # noqa: F821
        "Doctor", back_populates="queue_entries"
    )
    patient: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="queue_entries", foreign_keys=[patient_id]
    )
    deferred_from: Mapped["DoctorQueue | None"] = relationship(
        "DoctorQueue", remote_side="DoctorQueue.id"
    )
    symptoms: Mapped["Symptoms"] = relationship(  # noqa: F821
        "Symptoms", back_populates="queue_entry", uselist=False
    )
    post_visit_notes: Mapped["PostVisitNotes"] = relationship(  # noqa: F821
        "PostVisitNotes", back_populates="queue_entry", uselist=False
    )
    escalation_logs: Mapped[list["UrgencyEscalationLog"]] = relationship(
        "UrgencyEscalationLog", back_populates="queue_entry"
    )
    calendar_event: Mapped["CalendarEvent"] = relationship(  # noqa: F821
        "CalendarEvent", back_populates="queue_entry", uselist=False
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="queue_entry"
    )
    medication_reminders: Mapped[list["MedicationReminder"]] = relationship(  # noqa: F821
        "MedicationReminder", back_populates="queue_entry"
    )

    def __repr__(self) -> str:
        return (
            f"<DoctorQueue id={self.id} token={self.token_number} "
            f"status={self.status!r} tier={self.tier!r}>"
        )


class UrgencyEscalationLog(Base):
    """Audit trail of manual or AI-driven urgency tier changes."""

    __tablename__ = "urgency_escalation_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    queue_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), nullable=True
    )
    escalated_from_tier: Mapped[str | None] = mapped_column(String(10))
    escalated_to_tier: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(Text)
    escalated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # None = AI-driven escalation
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    queue_entry: Mapped[DoctorQueue] = relationship(
        "DoctorQueue", back_populates="escalation_logs"
    )


class DelayEvent(Base):
    """
    Delay detection events.

    Written by the delay detector after every consult completion
    when drift exceeds the configured threshold (default: 20 min).
    """

    __tablename__ = "delay_events"
    __table_args__ = (
        Index("idx_delay_events_doctor_date", "doctor_id", "appointment_date", "session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=False
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    session: Mapped[str] = mapped_column(String(10), nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
