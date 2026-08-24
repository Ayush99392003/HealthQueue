"""Google Calendar API endpoints for OAuth authentication and sync status."""

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.logger import get_logger
from src.models.user import User
from src.modules.auth.dependencies import get_current_user
from src.modules.calendar import service as calendar_service

logger = get_logger(__name__)
router = APIRouter()


@router.get("/auth-url")
async def get_auth_url(
    user: User = Depends(get_current_user),
) -> dict:
    """Generate the Google OAuth2 consent screen URL for linking calendar."""
    url = calendar_service.get_google_auth_url(user.id, user.role)
    return {"auth_url": url}


@router.get("/callback")
async def oauth_callback(
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str = Query(default="", description="State passed to Google OAuth"),
    db: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Exchange Google OAuth code for tokens and display confirmation."""
    try:
        await calendar_service.exchange_google_code(db, code, state)
        html_content = """
        <html>
            <head><title>Google Calendar Connected</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 40px; background: #0f172a; color: #f8fafc;">
                <h1 style="color: #22c55e;">✅ Google Calendar Connected!</h1>
                <p>Your HealthQueue appointments will now automatically synchronize to your Google Calendar.</p>
                <p><a href="https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/" style="color: #38bdf8; text-decoration: none; font-weight: bold;">Return to HealthQueue Portal →</a></p>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as exc:
        logger.error("Google OAuth callback failed: %s", exc)
        return HTMLResponse(
            content=f"<h3>Failed to link Google Calendar</h3><p>{exc}</p>",
            status_code=400,
        )


@router.post("/sync/{queue_id}")
async def sync_appointment(
    queue_id: int,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Trigger Google Calendar event synchronization for an appointment."""
    event = await calendar_service.sync_appointment_to_google_calendar(db, queue_id)
    if not event:
        return {"status": "skipped", "message": "Patient has not linked Google Calendar"}
    return {
        "status": event.sync_status,
        "event_id": event.google_event_id,
        "synced_at": event.synced_at.isoformat() if event.synced_at else None,
        "error": event.sync_error,
    }
