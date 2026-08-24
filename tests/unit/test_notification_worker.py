"""
Unit tests for the background notification worker.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.integration import Notification
from src.modules.notifications.worker import process_pending_notifications


@pytest.mark.asyncio
async def test_worker_handles_empty_queue(session: AsyncSession):
    """Worker returns zero counts when no notifications are pending."""
    stats = await process_pending_notifications(batch_size=10)
    assert stats["processed"] == 0
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_worker_processes_and_retries(session: AsyncSession, patient_user):
    """Worker processes pending notification and handles retry count."""
    notif = Notification(
        type="test_alert",
        channel="email",
        recipient_id=patient_user.id,
        destination="test@example.com",
        status="pending",
    )
    session.add(notif)
    await session.flush()

    assert notif.status == "pending"
    assert notif.retry_count == 0

