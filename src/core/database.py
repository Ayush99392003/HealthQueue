"""
Async SQLAlchemy 2.0 engine, session factory, and transaction helpers.

Invariants enforced here:
- Queue mutations MUST use get_serializable_session() for SERIALIZABLE isolation.
- All other read/write operations use get_db_session() (READ COMMITTED default).
- Never call session.commit() directly — use `async with session.begin():`.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)

settings = get_settings()

def _get_async_database_url() -> str:
    url = str(settings.database_url)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


_engine = create_async_engine(
    _get_async_database_url(),
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)


def get_engine():
    """Return the global async database engine."""
    return _engine

# ── Session Factories ─────────────────────────────────────────────────────────

_SessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

_SerializableSessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ── FastAPI Dependency ─────────────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a standard async DB session (READ COMMITTED).

    Use as a FastAPI dependency for all non-queue endpoints.
    """
    async with _SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_serializable_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager yielding a SERIALIZABLE isolation-level session.

    MUST be used for all token booking and queue mutation operations.
    Enforces pessimistic locking invariant (SELECT ... FOR UPDATE).

    Example::

        async with get_serializable_session() as session:
            async with session.begin():
                token = await session.execute(
                    select(DoctorQueue)
                    .where(...)
                    .with_for_update()
                )
    """
    async with _SerializableSessionFactory() as session:
        await session.execute(
            # Set SERIALIZABLE isolation for this connection
            __import__("sqlalchemy").text(
                "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
            )
        )
        try:
            yield session
        except Exception:
            await session.rollback()
            logger.error("Serializable transaction rolled back due to exception")
            raise


async def close_engine() -> None:
    """Dispose the engine connection pool — called on app shutdown."""
    await _engine.dispose()
    logger.info("Database engine disposed")
