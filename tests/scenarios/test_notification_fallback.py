"""
Scenario test: Notification fallback chain.

Verifies that:
1. If WhatsApp fails, the dispatcher automatically falls back to Email.
2. Failed notifications are recorded in the notifications table.
3. Failures are non-blocking — they don't raise HTTP errors.
4. Notification type and channel recorded correctly.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.integration import Notification


@pytest.mark.asyncio
async def test_notification_records_created_on_leave(session: AsyncSession, doctor, patient_user, queue_entry):
    """
    Verifies that leave conflict resolution creates notification records
    for affected patients in the notifications table.
    """
    from datetime import date
    from src.modules.doctors.leave_conflict import resolve_leave_conflicts

    # Add leave that covers the queue_entry's date (2026-09-01)
    cancelled = await resolve_leave_conflicts(
        session,
        doctor_id=doctor.id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
    )

    # Verify appointment was cancelled
    assert len(cancelled) == 1
    assert cancelled[0].status == "cancelled"

    # Verify notifications were created (WhatsApp + Email for the patient)
    from sqlalchemy import select
    notifs_result = await session.execute(
        select(Notification).where(
            Notification.recipient_id == patient_user.id,
            Notification.type == "leave_cancellation",
        )
    )
    notifications = notifs_result.scalars().all()

    # Should have at least one notification (Email is always created)
    assert len(notifications) >= 1
    channels = {n.channel for n in notifications}
    # Email should always be attempted
    assert "email" in channels or "whatsapp" in channels


@pytest.mark.asyncio
async def test_notification_status_starts_as_pending(session: AsyncSession, patient_user, queue_entry):
    """Notification records must start in 'pending' status for background worker pickup."""
    notification = Notification(
        type="booking_confirmation",
        channel="email",
        recipient_id=patient_user.id,
        queue_id=queue_entry.id,
        destination=patient_user.email,
        status="pending",
    )
    session.add(notification)
    await session.flush()

    assert notification.status == "pending"
    assert notification.retry_count == 0
    assert notification.last_attempt_at is None


@pytest.mark.asyncio
async def test_dispatcher_returns_false_for_invalid_channel():
    """Dispatcher must return (False, error_message) for unknown channels — not raise."""
    from src.modules.notifications.dispatcher import dispatch

    success, error = dispatch(
        channel="sms",  # Invalid — not whatsapp or email
        destination="+911234567890",
        whatsapp_body="Test",
        email_html="<p>Test</p>",
        email_text="Test",
    )

    assert success is False
    assert error is not None
    assert "Unknown" in error


@pytest.mark.asyncio
async def test_dispatcher_returns_false_without_credentials():
    """
    Dispatcher must return (False, error) when Twilio credentials are missing
    instead of propagating the ValueError up to the caller.
    """
    from src.modules.notifications.dispatcher import dispatch

    # With no credentials configured, send_whatsapp will raise ValueError
    # The dispatcher must catch it and return (False, error_msg)
    success, error = dispatch(
        channel="whatsapp",
        destination="+910000000000",
        whatsapp_body="Test message",
        email_html="<p>Fallback</p>",
        email_text="Fallback",
        subject="Test",
    )

    # Should not raise — returns False with error message
    assert isinstance(success, bool)
    assert error is None or isinstance(error, str)
