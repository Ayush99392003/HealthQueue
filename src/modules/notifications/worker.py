"""
Background notification worker.

Processes queued notifications (pending / retry status) in batches,
executes WhatsApp -> SMS -> Email fallback chain via dispatcher,
and updates status & delivery timestamps in PostgreSQL.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import _SessionFactory
from src.core.logger import get_logger
from src.models.integration import Notification
from src.modules.notifications.dispatcher import dispatch

logger = get_logger(__name__)

MAX_RETRIES = 3


async def process_pending_notifications(batch_size: int = 50) -> dict:
    """
    Process up to batch_size pending/retry notifications.

    Returns:
        {"processed": int, "sent": int, "failed": int, "retrying": int}
    """
    stats = {"processed": 0, "sent": 0, "failed": 0, "retrying": 0}

    async with _SessionFactory() as session:
        async with session.begin():
            # Query pending or retryable notifications
            result = await session.execute(
                select(Notification)
                .where(Notification.status.in_(["pending", "retry"]))
                .order_by(Notification.created_at.asc())
                .limit(batch_size)
            )
            notifications = result.scalars().all()

            if not notifications:
                return stats

            logger.info("Notification worker: Processing %d pending notifications", len(notifications))

            for notif in notifications:
                stats["processed"] += 1
                try:
                    success, error_msg = dispatch(
                        channel=notif.channel,
                        destination=notif.destination,
                        subject=f"HealthQueue Notification — {notif.type.replace('_', ' ').title()}",
                        whatsapp_body=notif.payload.get("message") if isinstance(notif.payload, dict) else "",
                        email_html=notif.payload.get("html") if isinstance(notif.payload, dict) else "",
                        email_text=notif.payload.get("text") if isinstance(notif.payload, dict) else "",
                    )

                    if success:
                        notif.status = "sent"
                        notif.sent_at = datetime.utcnow()
                        notif.error_message = None
                        stats["sent"] += 1
                        logger.info("Notification %d sent successfully to %s", notif.id, notif.destination)
                    else:
                        notif.retry_count = (notif.retry_count or 0) + 1
                        notif.error_message = error_msg
                        if notif.retry_count >= MAX_RETRIES:
                            notif.status = "failed"
                            stats["failed"] += 1
                            logger.error("Notification %d permanently failed after %d retries", notif.id, MAX_RETRIES)
                        else:
                            notif.status = "retry"
                            stats["retrying"] += 1
                            logger.warning("Notification %d scheduled for retry (%d/%d)", notif.id, notif.retry_count, MAX_RETRIES)

                except Exception as exc:
                    notif.retry_count = (notif.retry_count or 0) + 1
                    notif.error_message = str(exc)
                    notif.status = "failed" if notif.retry_count >= MAX_RETRIES else "retry"
                    stats["failed" if notif.status == "failed" else "retrying"] += 1
                    logger.warning("Notification worker exception for notif %d: %s", notif.id, exc)

    return stats
