"""
Dual-channel notification dispatcher.

Channel priority:
1. WhatsApp (Twilio) — real-time, actionable
2. Email (SMTP/SendGrid) — formal record

Fallback chain (AGENTS.md Invariant 5):
- WhatsApp fails → attempt Email dispatch
- Email fails → record status='pending' for background worker retry
- Max 3 tenacity retries each with exponential backoff + jitter
- All failures are logged and NON-BLOCKING
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_random_exponential,
)
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── WhatsApp (Twilio) ─────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def send_whatsapp(*, to: str, body: str) -> bool:
    """
    Send a WhatsApp message via Twilio.

    Retries up to 3 times with exponential backoff.
    Returns True on success.
    Raises TwilioRestException on exhausted retries.
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio credentials not configured — TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN required")

    client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
    to_formatted = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
    raw_from = settings.twilio_whatsapp_from or "+15614733679"
    from_formatted = f"whatsapp:{raw_from.replace('whatsapp:', '')}"

    message = client.messages.create(
        from_=from_formatted,
        to=to_formatted,
        body=body,
    )
    logger.info("WhatsApp sent — sid=%s to=%s", message.sid, to)
    return True


# ── Email (SMTP) ──────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def send_email(*, to: str, subject: str, html_body: str, text_body: str) -> bool:
    """
    Send an email via SMTP.

    Retries up to 3 times with exponential backoff.
    Returns True on success.
    """
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ValueError("SMTP credentials not configured — SMTP_HOST and SMTP_FROM_EMAIL required")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.sendmail(settings.smtp_from_email, to, msg.as_string())

    logger.info("Email sent — to=%s subject=%r", to, subject)
    return True


# ── Dispatcher ────────────────────────────────────────────────────────────────


def dispatch(
    *,
    channel: str,
    destination: str,
    subject: str = "",
    whatsapp_body: str = "",
    email_html: str = "",
    email_text: str = "",
) -> tuple[bool, str | None]:
    """
    Dispatch a notification on the specified channel with fallback.

    Fallback chain:
    - channel='whatsapp': try WhatsApp → on failure, try Email → on failure, return failed
    - channel='email': try Email → on failure, return failed

    Returns:
        (success: bool, error_message: str | None)
    """
    if channel == "whatsapp":
        try:
            send_whatsapp(to=destination, body=whatsapp_body)
            return True, None
        except (TwilioRestException, ValueError, Exception) as wa_exc:
            logger.error(
                "WhatsApp dispatch failed — falling back to Email. destination=%s error=%s",
                destination, wa_exc,
            )
            # Fallback: try email
            try:
                send_email(
                    to=destination,
                    subject=subject,
                    html_body=email_html,
                    text_body=email_text,
                )
                logger.info("WhatsApp→Email fallback succeeded for destination=%s", destination)
                return True, None
            except Exception as email_exc:
                err = f"WhatsApp: {wa_exc} | Email fallback: {email_exc}"
                logger.error("Both channels failed — destination=%s error=%s", destination, err)
                return False, err

    elif channel == "email":
        try:
            send_email(
                to=destination,
                subject=subject,
                html_body=email_html,
                text_body=email_text,
            )
            return True, None
        except Exception as exc:
            logger.error("Email dispatch failed — destination=%s error=%s", destination, exc)
            return False, str(exc)

    else:
        err = f"Unknown notification channel: {channel!r}"
        logger.error(err)
        return False, err
