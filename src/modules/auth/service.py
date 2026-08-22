"""
Auth service — bcrypt password hashing and JWT token management.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from src.core.config import get_settings
from src.core.exceptions import UnauthorizedError
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── Password Hashing ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode(), salt).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT Tokens ────────────────────────────────────────────────────────────────


def create_access_token(user_id: int, role: str) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    logger.debug("Access token created for user_id=%s role=%s", user_id, role)
    return token


def create_refresh_token(user_id: int) -> str:
    """Create a signed JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Raises:
        UnauthorizedError: If token is invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise UnauthorizedError("Invalid or expired token") from exc
