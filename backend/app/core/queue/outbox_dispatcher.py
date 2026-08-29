import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue.interfaces import DurableTaskQueue
from app.documents.infrastructure.persistence.models import SQLAlchemyOutboxEvent

logger = logging.getLogger(__name__)


class OutboxDispatcher:
    def __init__(self, db: AsyncSession, task_queue: DurableTaskQueue) -> None:
        self._db = db
        self._queue = task_queue

    async def dispatch_pending_events(self, limit: int = 50) -> int:
        """
        Scans for PENDING outbox events, publishes them to Redis message queue,
        and marks them PUBLISHED atomically.
        """
        stmt = (
            select(SQLAlchemyOutboxEvent)
            .where(SQLAlchemyOutboxEvent.status == "PENDING")
            .order_by(SQLAlchemyOutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._db.execute(stmt)
        events = result.scalars().all()

        dispatched_count = 0
        now = datetime.now(UTC)

        for event in events:
            try:
                # Deduplication / Idempotency key
                idempotency_key = f"{event.user_id}:{event.document_id}:{event.document_version}:{event.event_type}"
                payload = dict(event.payload_json or {})
                payload["idempotency_key"] = idempotency_key
                payload["outbox_event_id"] = str(event.id)

                await self._queue.enqueue(
                    task_type=event.event_type,
                    payload=payload,
                )

                event.status = "PUBLISHED"
                event.published_at = now
                dispatched_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to dispatch outbox event {event.id} ({event.event_type}): {str(e)}",
                    exc_info=True,
                )
                # Event remains PENDING to be retried on subsequent reconciliation

        await self._db.flush()
        return dispatched_count
