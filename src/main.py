"""
FastAPI application entrypoint.

Startup:
1. Configure rich logging
2. Validate all settings (fails immediately if .env is missing required vars)
3. Register exception handlers
4. Mount API routers
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.database import close_engine
from src.core.exceptions import register_exception_handlers
from src.core.logger import configure_logging, get_logger

# ── Bootstrap logging before anything else ────────────────────────────────────
configure_logging()
logger = get_logger(__name__)
settings = get_settings()  # Validates all env vars — raises ValidationError if incomplete


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    """Application lifespan — startup and shutdown hooks."""
    logger.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    # Auto-initialize database tables
    try:
        from src.core.database import get_engine
        import src.models  # Register all models with Base.metadata
        from src.models.base import Base
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized/verified.")
    except Exception as exc:
        logger.warning("Could not auto-create database tables on startup: %s", exc)

    yield
    logger.info("Shutting down — disposing database engine")
    await close_engine()


# ── App Factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Intelligent token-based clinical queue with AI triage, "
        "dynamic ETA reflow, and dual-channel notifications."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https://.*\.vercel\.app.*|http://localhost.*|http://127\.0\.0\.1.*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Exception Handlers ────────────────────────────────────────────────────────

register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────

from src.api.v1 import admin, auth, calendar as calendar_router, clinical, doctors  # noqa: E402
from src.api.v1 import queue as queue_router  # noqa: E402

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(doctors.router, prefix="/api/v1/doctors", tags=["Doctors"])
app.include_router(queue_router.router, prefix="/api/v1/queue", tags=["Queue"])
app.include_router(clinical.router, prefix="/api/v1/clinical", tags=["Clinical"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(calendar_router.router, prefix="/api/v1/calendar", tags=["Calendar"])


# ── Health Check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe — returns 200 OK when the service is running."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
    }
