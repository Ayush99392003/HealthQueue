"""
Domain exceptions and centralized FastAPI error handlers.

Error Handling Invariants:
- Missing/corrupt input data → 422 Unprocessable Entity (blocking, client error)
- Concurrency collision → 409 Conflict (with internal retries exhausted)
- AI/LLM failures → logged, non-blocking, fallback state preserved
- Notification failures → logged, non-blocking, retried by background worker
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.core.logger import get_logger

logger = get_logger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────


class AppError(Exception):
    """Base exception for all domain errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    """Booking concurrency conflict — serialization collision exhausted retries."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "BOOKING_CONFLICT"


class ValidationError(AppError):
    """Required data missing or invalid — strict stop-and-reject, never mock."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"


class UnauthorizedError(AppError):
    """Missing or invalid authentication token."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    """Authenticated but insufficient role permissions."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class DoctorNotAvailableError(AppError):
    """Doctor has no availability or is on approved leave for the requested date."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "DOCTOR_NOT_AVAILABLE"


class QueueFullError(AppError):
    """All token slots for the doctor's session are booked."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "QUEUE_FULL"


class LLMExtractionError(AppError):
    """
    LLM extraction failed after all retries.

    NON-BLOCKING — callers must handle this gracefully and
    persist raw input text while marking is_processed=False.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "LLM_UNAVAILABLE"


class NotificationError(AppError):
    """
    Notification dispatch failed after all retries.

    NON-BLOCKING — recorded in notifications table for background retry.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "NOTIFICATION_FAILED"


class CalendarSyncError(AppError):
    """
    Google Calendar sync failed.

    NON-BLOCKING — recorded in calendar_events.sync_error.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "CALENDAR_SYNC_FAILED"


# ── FastAPI Error Handler Registration ────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register all domain exception handlers with the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.error(
            "Domain error: %s — %s",
            exc.error_code,
            exc.message,
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
            },
        )
