import asyncio
import logging
import time
from typing import Any

from app.core.queue.interfaces import Job, JobDispatcher, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.retry import calculate_backoff

logger = logging.getLogger(__name__)


class QueueWorker:
    """
    Asynchronous queue worker engine consuming Redis Streams.
    Handles message dispatch, exponential retry backoff, DLQ routing,
    and automatic recovery of orphaned pending messages.
    """

    def __init__(
        self,
        task_queue: RedisStreamTaskQueue,
        dispatcher: JobDispatcher,
        concurrency: int = 4,
        block_ms: int = 2000,
        visibility_timeout_s: int = 60,
        retry_base_delay: float = 2.0,
        retry_max_delay: float = 60.0,
        recovery_interval_s: float = 15.0,
        retry_pump_interval_s: float = 2.0,
    ) -> None:
        self._task_queue = task_queue
        self._dispatcher = dispatcher
        self._concurrency = max(1, concurrency)
        self._block_ms = block_ms
        self._visibility_timeout_ms = int(visibility_timeout_s * 1000)
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._recovery_interval_s = recovery_interval_s
        self._retry_pump_interval_s = retry_pump_interval_s

        self._is_running = False
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._in_flight_tasks: set[asyncio.Task[Any]] = set()

        self._consume_task: asyncio.Task[None] | None = None
        self._recovery_task: asyncio.Task[None] | None = None
        self._pump_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def active_tasks_count(self) -> int:
        return len(self._in_flight_tasks)

    async def start(self) -> None:
        """
        Starts the worker consumption, retry pump, and orphan recovery loops.
        """
        if self._is_running:
            return

        self._is_running = True
        await self._task_queue.ensure_consumer_group()

        self._consume_task = asyncio.create_task(
            self._consume_loop(), name="queue_consume_loop"
        )
        self._recovery_task = asyncio.create_task(
            self._recovery_loop(), name="queue_recovery_loop"
        )
        self._pump_task = asyncio.create_task(
            self._retry_pump_loop(), name="queue_retry_pump_loop"
        )

        logger.info(
            f"QueueWorker started: consumer={self._task_queue.consumer_name} "
            f"stream={self._task_queue.stream_name} group={self._task_queue.consumer_group} "
            f"concurrency={self._concurrency}"
        )

    async def stop(self, timeout_seconds: float = 5.0) -> None:
        """
        Gracefully stops the worker without acknowledging unfinished in-flight jobs.
        """
        if not self._is_running:
            return

        logger.info(
            f"Initiating graceful shutdown for QueueWorker ({self._task_queue.consumer_name})..."
        )
        self._is_running = False

        # Cancel background loops
        for loop_task in (self._consume_task, self._recovery_task, self._pump_task):
            if loop_task and not loop_task.done():
                loop_task.cancel()

        # Wait for in-flight job tasks to complete up to timeout
        if self._in_flight_tasks:
            logger.info(
                f"Waiting for {len(self._in_flight_tasks)} in-flight job(s) to finish..."
            )
            _, pending = await asyncio.wait(
                self._in_flight_tasks, timeout=timeout_seconds
            )
            for pending_task in pending:
                logger.warning(
                    "In-flight job task did not complete in grace period; cancelling. Message remains un-ACKed in PEL."
                )
                pending_task.cancel()

        self._in_flight_tasks.clear()
        logger.info("QueueWorker shutdown completed.")

    async def _consume_loop(self) -> None:
        """Continuously polls new messages from the stream using XREADGROUP."""
        while self._is_running:
            try:
                # Read batch up to available semaphore slots
                messages = await self._task_queue.read_messages(
                    count=self._concurrency, block_ms=self._block_ms
                )
                if not messages:
                    continue

                for msg_id, job in messages:
                    if not self._is_running:
                        break
                    task = asyncio.create_task(self.handle_message(msg_id, job))
                    self._in_flight_tasks.add(task)
                    task.add_done_callback(self._in_flight_tasks.discard)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in QueueWorker consume loop: {e}")
                await asyncio.sleep(1.0)

    async def _recovery_loop(self) -> None:
        """Periodically recovers orphaned pending messages via XAUTOCLAIM."""
        while self._is_running:
            try:
                await asyncio.sleep(self._recovery_interval_s)
                if not self._is_running:
                    break

                start_id = "0-0"
                while self._is_running:
                    next_id, claimed = await self._task_queue.reclaim_orphaned_jobs(
                        min_idle_time_ms=self._visibility_timeout_ms,
                        count=10,
                        start_id=start_id,
                    )
                    if not claimed:
                        break

                    for msg_id, job in claimed:
                        task = asyncio.create_task(
                            self.handle_message(msg_id, job, is_reclaimed=True)
                        )
                        self._in_flight_tasks.add(task)
                        task.add_done_callback(self._in_flight_tasks.discard)

                    if next_id == "0-0" or next_id == start_id:
                        break
                    start_id = next_id

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in orphan recovery loop: {e}")

    async def _retry_pump_loop(self) -> None:
        """Periodically pumps due retries from sorted set back into the stream."""
        while self._is_running:
            try:
                await asyncio.sleep(self._retry_pump_interval_s)
                if not self._is_running:
                    break
                await self._task_queue.pump_scheduled_retries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry pump loop: {e}")

    async def handle_message(
        self, msg_id: str, job: Job, is_reclaimed: bool = False
    ) -> JobResult:
        """
        Executes a single job with concurrency management, retry scheduling, and DLQ routing.
        """
        async with self._semaphore:
            start_time = time.time()
            logger.info(
                f"queue.job_started: job_id={job.job_id} task_type={job.task_type} "
                f"attempt={job.attempt}/{job.max_attempts} stream_msg_id={msg_id} "
                f"reclaimed={is_reclaimed}"
            )

            try:
                result = await self._dispatcher.dispatch(job)
            except Exception as unhandled_err:
                logger.exception(
                    f"Unhandled exception during job execution {job.job_id}: {unhandled_err}"
                )
                result = JobResult(
                    success=False, error=str(unhandled_err), retryable=True
                )

            duration_ms = (time.time() - start_time) * 1000

            if result.success:
                await self._task_queue.acknowledge(msg_id)
                logger.info(
                    f"queue.job_completed: job_id={job.job_id} task_type={job.task_type} "
                    f"attempt={job.attempt}/{job.max_attempts} duration_ms={duration_ms:.2f}"
                )
                return result

            # Failure handling
            error_msg = result.error or "Unknown failure"
            if result.retryable and job.attempt < job.max_attempts:
                backoff_delay = calculate_backoff(
                    job.attempt,
                    base_delay=self._retry_base_delay,
                    max_delay=self._retry_max_delay,
                )
                await self._task_queue.schedule_retry(job, error_msg, backoff_delay)
                # Acknowledge the old stream message since it has been transferred to retry set
                await self._task_queue.acknowledge(msg_id)
            else:
                error_type = (
                    "MaxAttemptsExceeded"
                    if job.attempt >= job.max_attempts
                    else "NonRetryableError"
                )
                await self._task_queue.route_to_dead_letter(
                    job, error_msg, error_type=error_type
                )
                # Acknowledge the old stream message since it is now stored in DLQ
                await self._task_queue.acknowledge(msg_id)

            return result
