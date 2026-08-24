"""
Async SQLAlchemy 2.0 engine, session factory, and transaction helpers.

Invariants enforced here:
- Queue mutations MUST use get_serializable_session() for SERIALIZABLE isolation.
- All other read/write operations use get_db_session() (READ COMMITTED default).
- Never call session.commit() directly — use `async with session.begin():`.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.logger import get_logger

logger = get_logger(__name__)


def _resolve_database_url() -> str:
    """
    Resolve the async database URL with Railway-resilient fallback chain:

    1. DATABASE_URL from os.environ (explicit env var or Railway reference)
    2. Construct from PG* individual vars (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD)
       which Railway always injects when a PostgreSQL service is connected
    3. pydantic-settings / .env file
    4. SQLite fallback (dev only)
    """
    # Priority 1: DATABASE_URL env var (most common)
    raw = os.environ.get("DATABASE_URL", "").strip()

    # Priority 2: Build from individual PG* vars (Railway always injects these)
    if not raw:
        pghost = os.environ.get("PGHOST", "")
        pgport = os.environ.get("PGPORT", "5432")
        pgdb = os.environ.get("PGDATABASE", "")
        pguser = os.environ.get("PGUSER", "")
        pgpass = os.environ.get("PGPASSWORD", "")
        if pghost and pgdb and pguser:
            raw = f"postgresql://{pguser}:{pgpass}@{pghost}:{pgport}/{pgdb}"
            logger.info("Database: Built PostgreSQL URL from PG* environment variables (Railway).")

    # Priority 3: pydantic-settings / .env fallback
    if not raw:
        try:
            from src.core.config import get_settings
            raw = str(get_settings().database_url).strip()
        except Exception:
            pass

    if not raw:
        raw = ""

    if raw.startswith("postgresql+asyncpg://"):
        logger.info("Database: PostgreSQL (asyncpg) — ready.")
        return raw
    if raw.startswith("postgresql://"):
        logger.info("Database: PostgreSQL — converting to asyncpg driver.")
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        logger.info("Database: PostgreSQL (Railway/Heroku) — converting to asyncpg driver.")
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw.startswith("sqlite"):
        logger.warning(
            "⚠️  DATABASE: SQLite — data is ephemeral and WILL be wiped on restart! "
            "Connect a PostgreSQL service in Railway and set DATABASE_URL."
        )
        return raw

    logger.warning(
        "⚠️  DATABASE: No valid DATABASE_URL found ('%s') — falling back to SQLite. "
        "Set DATABASE_URL or connect a PostgreSQL plugin in Railway.",
        raw[:40] if raw else "empty",
    )
    return "sqlite+aiosqlite:///./healthqueue.db"


# ── Engine ────────────────────────────────────────────────────────────────────

_DB_URL = _resolve_database_url()
_IS_POSTGRES = _DB_URL.startswith("postgresql")

def _build_engine():
    kwargs = {"echo": os.environ.get("DEBUG", "false").lower() == "true"}
    if _IS_POSTGRES:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
    return create_async_engine(_DB_URL, **kwargs)


_engine = _build_engine()


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

# SERIALIZABLE isolation only supported by PostgreSQL (asyncpg).
# SQLite is SERIALIZABLE by default and does not accept execution_options isolation_level.
_serializable_kwargs: dict = {}
if _IS_POSTGRES:
    _serializable_kwargs["execution_options"] = {"isolation_level": "SERIALIZABLE"}

_SerializableSessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    **_serializable_kwargs,
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
    Context manager yielding a SERIALIZABLE isolation-level async session.

    MUST be used for all token booking and queue mutation operations.

    On PostgreSQL: isolation_level=SERIALIZABLE is set via execution_options
    on the session factory (correct SQLAlchemy 2.0 async approach).

    On SQLite (dev/test): SQLite is SERIALIZABLE by default — no extra config needed.

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
