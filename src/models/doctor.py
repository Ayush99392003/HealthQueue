"""Doctor, availability, and leave models."""

from datetime import date, time

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Doctor(Base, TimestampMixin):
    """
    Doctor profile — extends users with clinical and scheduling config.

    booking_mode controls token allocation strategy:
      - walk_in: no advance bookings, pure queue
      - advance_only: all tokens pre-booked with explicit times
      - hybrid: mix of anchor (advance) + open queue tokens
    """

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )
    specialisation: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    experience_years: Mapped[int | None] = mapped_column(Integer)

    # Consultation duration configuration
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    avg_consult_minutes: Mapped[float | None] = mapped_column(Numeric(5, 2))
    consult_sample_size: Mapped[int] = mapped_column(Integer, default=0)

    # Queue mode and capacity allocation percentages
    booking_mode: Mapped[str] = mapped_column(
        String(15), nullable=False, default="hybrid"
    )  # walk_in | advance_only | hybrid
    anchor_slot_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=25.00)
    priority_slot_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=25.00)
    emergency_slot_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=10.00)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="doctor_profile"
    )
    availability: Mapped[list["DoctorAvailability"]] = relationship(
        "DoctorAvailability", back_populates="doctor", cascade="all, delete-orphan"
    )
    leaves: Mapped[list["DoctorLeave"]] = relationship(
        "DoctorLeave", back_populates="doctor", cascade="all, delete-orphan"
    )
    queue_entries: Mapped[list["DoctorQueue"]] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="doctor"
    )

    def __repr__(self) -> str:
        return f"<Doctor id={self.id} specialisation={self.specialisation!r}>"


class DoctorAvailability(Base):
    """
    Weekly recurring schedule for a doctor's working sessions.

    day_of_week: 0=Monday … 6=Sunday
    session: morning | evening | full_day
    """

    __tablename__ = "doctor_availability"
    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", "session", name="uq_availability"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    session: Mapped[str] = mapped_column(String(10), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped[Doctor] = relationship("Doctor", back_populates="availability")


class DoctorLeave(Base, TimestampMixin):
    """Approved leave date ranges — used to block queue slot creation."""

    __tablename__ = "doctor_leave"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doctors.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    doctor: Mapped[Doctor] = relationship("Doctor", back_populates="leaves")
