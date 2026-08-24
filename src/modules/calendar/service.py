"""
Google Calendar OAuth 2.0 and Event Synchronization Service.

Handles:
- OAuth2 authorization URL generation
- Token exchange and storage
- Creating, updating, and deleting Google Calendar events for appointments
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logger import get_logger
from src.models.doctor import Doctor
from src.models.integration import CalendarEvent, OAuthToken
from src.models.queue import DoctorQueue
from src.models.user import User

logger = get_logger(__name__)
settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_google_auth_url(user_id: int, role: str) -> str:
    """Generate the Google OAuth2 consent screen URL."""
    if not settings.google_client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured in settings")

    state = json.dumps({"user_id": user_id, "role": role})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri or "https://healthqueue-production.up.railway.app/api/v1/calendar/callback",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_google_code(db: AsyncSession, code: str, state_json: str) -> OAuthToken:
    """Exchange authorization code for access and refresh tokens and save to DB."""
    redirect_uri = settings.google_redirect_uri or "https://healthqueue-production.up.railway.app/api/v1/calendar/callback"

    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))

    state = json.loads(state_json) if state_json else {}
    user_id = state.get("user_id", 1)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Check if OAuthToken already exists for user
    res = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == "google",
        )
    )
    existing_token = res.scalar_one_or_none()

    if existing_token:
        existing_token.access_token = access_token
        if refresh_token:
            existing_token.refresh_token = refresh_token
        existing_token.expires_at = expires_at
        await db.commit()
        return existing_token
    else:
        new_token = OAuthToken(
            user_id=user_id,
            provider="google",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=SCOPES,
        )
        db.add(new_token)
        await db.commit()
        return new_token


async def sync_appointment_to_google_calendar(
    db: AsyncSession,
    queue_id: int,
) -> CalendarEvent | None:
    """Create or update a Google Calendar event for a booked appointment."""
    q_res = await db.execute(select(DoctorQueue).where(DoctorQueue.id == queue_id))
    q_entry = q_res.scalar_one_or_none()
    if not q_entry:
        return None

    # Fetch doctor and patient info
    doc_res = await db.execute(select(Doctor).where(Doctor.id == q_entry.doctor_id))
    doctor = doc_res.scalar_one_or_none()

    patient_res = await db.execute(select(User).where(User.id == q_entry.patient_id))
    patient = patient_res.scalar_one_or_none()

    # Fetch patient's Google OAuth Token
    token_res = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == q_entry.patient_id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = token_res.scalar_one_or_none()
    if not oauth_token or not oauth_token.access_token:
        logger.info("Patient #%s has not linked Google Calendar — skipping sync", q_entry.patient_id)
        return None

    # Calculate event start and end
    appt_date = q_entry.appointment_date
    start_time_str = q_entry.anchor_time.strftime("%H:%M:%S") if q_entry.anchor_time else "09:30:00"
    start_iso = f"{appt_date}T{start_time_str}Z"
    end_iso = f"{appt_date}T10:00:00Z"

    event_body = {
        "summary": f"🏥 Clinical Appointment - Token #{q_entry.token_number}",
        "description": (
            f"HealthQueue Clinical Appointment\n"
            f"Doctor ID: #{q_entry.doctor_id} ({doctor.specialisation if doctor else 'Specialist'})\n"
            f"Token: #{q_entry.token_number} | Tier: {q_entry.tier}\n"
            f"Status: {q_entry.status}\n"
            f"Live Queue Tracking: https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/"
        ),
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "email", "minutes": 60},
            ],
        },
    }

    try:
        req = urllib.request.Request(
            GOOGLE_CALENDAR_API_URL,
            data=json.dumps(event_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {oauth_token.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            google_event = json.loads(resp.read().decode("utf-8"))

        event_id = google_event.get("id", "")
        cal_event = CalendarEvent(
            queue_id=q_entry.id,
            google_event_id=event_id,
            sync_status="synced",
            synced_at=datetime.utcnow(),
        )
        db.add(cal_event)
        await db.commit()
        logger.info("Google Calendar event created — event_id=%s queue_id=%s", event_id, queue_id)
        return cal_event

    except Exception as exc:
        logger.warning("Google Calendar event creation failed (non-blocking): %s", exc)
        cal_event = CalendarEvent(
            queue_id=q_entry.id,
            google_event_id="",
            sync_status="failed",
            sync_error=str(exc),
        )
        db.add(cal_event)
        await db.commit()
        return cal_event
