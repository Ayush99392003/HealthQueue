"""Integration models: notifications, calendar events, OAuth tokens, LLM call log."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    """
    Dual-channel notification record (email | whatsapp).

    Fallback chain:
    - WhatsApp fails → downgrade to Email dispatch
    - Email fails → mark status=pending for background worker retry
    - status=failed_permanent after all retries exhausted
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_status", "status"),
        Index("idx_notifications_type", "type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # booking_confirmation | delay_update | cancellation | post_visit |
    # medication_reminder | leave_cancellation
    channel: Mapped[str] = mapped_column(String(10), nullable=False, default="email")
    # email | whatsapp
    recipient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    queue_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), nullable=True
    )
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    # pending | sent | failed | failed_permanent
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    recipient: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="notifications"
    )
    queue_entry: Mapped["DoctorQueue"] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="notifications"
    )


class CalendarEvent(Base, TimestampMixin):
    """
    Google Calendar event tracking per queue entry.

    sync_error stores the error message if the Calendar API failed.
    The booking flow continues even if sync_error is set (non-blocking).
    """

    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), unique=True, nullable=False
    )
    google_event_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    doctor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(10), default="created")
    # created | updated | deleted
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    queue_entry: Mapped["DoctorQueue"] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="calendar_event"
    )


class OAuthToken(Base, TimestampMixin):
    """
    Encrypted Google OAuth 2.0 token storage.

    access_token and refresh_token are encrypted at rest (Fernet).
    """

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # google
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="oauth_tokens")  # noqa: F821


class LLMCallLog(Base):
    """
    Observability log for every LLM router call.

    Written whether the call succeeds or fails (after retries exhausted).
    Used for monitoring provider reliability and latency trends.
    """

    __tablename__ = "llm_call_log"
    __table_args__ = (
        Index("idx_llm_log_provider", "provider", "call_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # groq | azure | gemini | openai | anthropic
    call_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # pre_visit | post_visit
    queue_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("doctor_queue.id"), nullable=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
