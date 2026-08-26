import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.queue.interfaces import DurableTaskQueue, Job, JobDispatcher

logger = logging.getLogger(__name__)


class InMemoryDurableTaskQueue(DurableTaskQueue):
    """
    In-memory task queue implementation for unit tests and local non-Redis development.
    Preserves serializable Job contracts and allows synchronous or asynchronous job dispatch.
    """

    def __init__(self, dispatcher: JobDispatcher | None = None, auto_dispatch: bool = False) -> None:
        self._dispatcher = dispatcher
        self._auto_dispatch = auto_dispatch
        self._jobs: dict[UUID, Job] = {}
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._acknowledged: set[UUID] = set()
        self._dead_letter: list[dict[str, Any]] = []
        self._retries: list[tuple[float, Job]] = []

    @property
    def jobs(self) -> dict[UUID, Job]:
        return self._jobs

    @property
    def dead_letter_jobs(self) -> list[dict[str, Any]]:
        return self._dead_letter

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
        correlation_id: str | None = None,
        job_id: UUID | None = None,
    ) -> Job:
        job = Job(
            job_id=job_id or uuid4(),
            task_type=task_type,
            payload=payload,
            attempt=1,
            max_attempts=max_attempts,
            created_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        self._jobs[job.job_id] = job
        await self._queue.put(job)

        if self._auto_dispatch and self._dispatcher:
            # Synchronously execute handler for deterministic test flows
            result = await self._dispatcher.dispatch(job)
            if result.success:
                await self.acknowledge(job.job_id)
            elif result.retryable and job.attempt < job.max_attempts:
                await self.schedule_retry(job, result.error or "Error", delay_seconds=0.0)
            else:
                await self.route_to_dead_letter(job, result.error or "Error")

        return job

    async def acknowledge(self, job_id_or_msg_id: str | UUID) -> None:
        if isinstance(job_id_or_msg_id, str):
            try:
                uid = UUID(job_id_or_msg_id)
            except ValueError:
                return
        else:
            uid = job_id_or_msg_id
        self._acknowledged.add(uid)

    async def reject(self, job_id: UUID, error: str, retryable: bool = True) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if retryable and job.attempt < job.max_attempts:
            await self.schedule_retry(job, error, delay_seconds=0.0)
        else:
            await self.route_to_dead_letter(job, error)

    async def schedule_retry(self, job: Job, error: str, delay_seconds: float = 0.0) -> None:
        job.attempt += 1
        self._retries.append((time.time() + delay_seconds, job))

    async def route_to_dead_letter(
        self, job: Job, error: str, error_type: str | None = None
    ) -> None:
        self._dead_letter.append(
            {
                "job_id": str(job.job_id),
                "task_type": job.task_type,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                "error": error,
                "error_type": error_type or "Failure",
                "dead_lettered_at": datetime.now(UTC).isoformat(),
            }
        )
