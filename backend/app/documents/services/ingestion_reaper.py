import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.queue.interfaces import DurableTaskQueue
from app.documents.domain.models import DocumentStatus
from app.documents.infrastructure.persistence.models import SQLAlchemyDocument

logger = logging.getLogger(__name__)


class DurableIngestionReaper:
    """
    Reconciliation worker that discovers stale QUEUED documents (e.g. created when
    Redis was unreachable or due to application crashes before XADD) and re-enqueues
    them into the DurableTaskQueue.

    Operates under an At-Least-Once reconciliation model (Option A). Multiple instances
    may concurrently discover and re-enqueue stale documents; this is safe because
    downstream document processing is strictly idempotent and protected by PostgreSQL row locks.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Any,
        task_queue: DurableTaskQueue,
        stale_threshold_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._task_queue = task_queue
        self._stale_threshold_seconds = stale_threshold_seconds

    async def reap(self, limit: int = 50) -> int:
        """
        Scans for documents stuck in 'queued' status older than stale_threshold_seconds
        and re-enqueues them for processing.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self._stale_threshold_seconds)
        reaped_count = 0

        async with self._session_factory() as session:
            stmt = (
                select(SQLAlchemyDocument)
                .where(
                    SQLAlchemyDocument.status == DocumentStatus.QUEUED.value,
                    SQLAlchemyDocument.created_at <= cutoff,
                )
                .order_by(SQLAlchemyDocument.created_at.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            stale_docs = result.scalars().all()

            for doc in stale_docs:
                try:
                    await self._task_queue.enqueue(
                        task_type="PROCESS_DOCUMENT",
                        payload={
                            "document_id": str(doc.id),
                            "user_id": str(doc.user_id),
                            "checksum": doc.checksum,
                            "scope": doc.scope,
                        },
                        max_attempts=3,
                    )
                    reaped_count += 1
                    logger.info(
                        f"ingestion.reaper_recovered_document: document_id={doc.id} "
                        f"user_id={doc.user_id} created_at={doc.created_at.isoformat()}"
                    )
                except Exception as ex:
                    logger.error(
                        f"Failed to re-enqueue stale document {doc.id} during reaping: {ex}"
                    )

        if reaped_count > 0:
            try:
                from app.core.telemetry import QUEUE_REAPER_RECOVERED

                QUEUE_REAPER_RECOVERED.inc(reaped_count)
            except Exception:
                pass
            logger.info(f"ingestion.reaper_cycle_completed: recovered={reaped_count}")
        return reaped_count

    async def run_loop(
        self,
        interval_seconds: float = 60.0,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """
        Periodically executes the reap cycle until cancelled or stop_event is set.
        """
        logger.info(
            f"Starting DurableIngestionReaper loop (interval={interval_seconds}s, threshold={self._stale_threshold_seconds}s)"
        )
        while stop_event is None or not stop_event.is_set():
            try:
                await self.reap()
            except asyncio.CancelledError:
                logger.info("DurableIngestionReaper loop received cancellation.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in DurableIngestionReaper loop: {e}")

            try:
                if stop_event is not None:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                    break
                else:
                    await asyncio.sleep(interval_seconds)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
