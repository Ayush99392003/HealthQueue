"""User model — patients, doctors, and admins."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Unified user table for all roles."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # patient|doctor|admin
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    doctor_profile: Mapped["Doctor"] = relationship(  # noqa: F821
        "Doctor", back_populates="user", uselist=False
    )
    queue_entries: Mapped[list["DoctorQueue"]] = relationship(  # noqa: F821
        "DoctorQueue", back_populates="patient", foreign_keys="DoctorQueue.patient_id"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="recipient"
    )
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(  # noqa: F821
        "OAuthToken", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
