"""Auth API router — register and login endpoints."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.exceptions import ConflictError, UnauthorizedError
from src.core.logger import get_logger
from src.models.user import User
from src.modules.auth.service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()


# ── Request / Response Schemas ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str  # patient | doctor | admin
    first_name: str
    last_name: str
    phone: str | None = None
    whatsapp_number: str | None = None
    # Required only when registering as doctor or admin
    admin_secret: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    Register a new user account.

    Raises:
        ConflictError: If email is already registered.
        ValidationError: If role is not one of patient|doctor|admin.
    """
    if body.role not in {"patient", "doctor", "admin"}:
        from src.core.exceptions import ValidationError
        raise ValidationError(f"Invalid role: {body.role!r}. Must be patient, doctor, or admin.")

    # Admin and Doctor registration require the admin_registration_secret
    if body.role in {"admin", "doctor"}:
        expected_secret = settings.admin_registration_secret or "admin2026"
        if not body.admin_secret or body.admin_secret != expected_secret:
            from src.core.exceptions import ValidationError
            raise ValidationError(
                f"Staff passcode required for {body.role} role. Please enter 'admin2026' (or your clinic's security passcode)."
            )

    # Check for duplicate email
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Email {body.email!r} is already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        whatsapp_number=body.whatsapp_number,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info("New user registered — id=%s email=%s role=%s", user.id, user.email, user.role)

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    Authenticate a user and return JWT tokens.

    Raises:
        UnauthorizedError: If email not found or password is incorrect.
    """
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        logger.warning("Failed login attempt for email=%s", body.email)
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is deactivated. Please contact support.")

    logger.info("User logged in — id=%s role=%s", user.id, user.role)

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
    )
