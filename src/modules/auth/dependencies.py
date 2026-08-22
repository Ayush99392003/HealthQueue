"""FastAPI dependencies — current user extraction and role enforcement."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.logger import get_logger
from src.models.user import User
from src.modules.auth.service import decode_token

logger = get_logger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """
    FastAPI dependency: extract and validate the current authenticated user.

    Raises:
        UnauthorizedError: If token is invalid or user not found/inactive.
    """
    payload = decode_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        logger.warning("Token valid but user not found or inactive — user_id=%s", user_id)
        raise UnauthorizedError("User account not found or deactivated")

    return user


def require_role(*roles: str):
    """
    FastAPI dependency factory: enforce that the current user has one of the given roles.

    Usage::

        @router.get("/admin/stats")
        async def get_stats(user: User = Depends(require_role("admin"))):
            ...
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            logger.warning(
                "Role check failed — user_id=%s role=%s required=%s",
                user.id,
                user.role,
                roles,
            )
            raise ForbiddenError(
                f"Access denied. Required role: {' or '.join(roles)}"
            )
        return user

    return _check
