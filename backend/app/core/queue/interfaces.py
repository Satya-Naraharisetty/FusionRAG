import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    ENQUEUED = "ENQUEUED"
    PROCESSING = "PROCESSING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class Job(BaseModel):
    """
    Serializable job contract for durable execution.
    Contains strictly serializable metadata and IDs — never python callables or raw binaries.
    """

    job_id: UUID = Field(default_factory=uuid4)
    task_type: str
    payload: dict[str, Any]
    attempt: int = 1
    max_attempts: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Returns a JSON-serializable dictionary representation."""
        return {
            "job_id": str(self.job_id),
            "task_type": self.task_type,
            "payload": self.payload,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        """Reconstructs a Job from a dictionary."""
        return cls(
            job_id=UUID(str(data["job_id"])),
            task_type=data["task_type"],
            payload=data.get("payload", {}),
            attempt=int(data.get("attempt", 1)),
            max_attempts=int(data.get("max_attempts", 3)),
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at", datetime.now(UTC)),
            correlation_id=data.get("correlation_id"),
        )


class JobResult(BaseModel):
    """Result returned by a JobHandler after execution."""

    success: bool
    error: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class JobHandler(ABC):
    """Abstract handler for a specific task type."""

    @abstractmethod
    async def handle(self, job: Job) -> JobResult:
        """Executes the business logic for the given job."""
        pass


class JobDispatcher:
    """
    Dispatches jobs to registered handlers based on task_type.
    Decouples queue worker infrastructure from business logic.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, task_type: str, handler: JobHandler) -> None:
        if not task_type or not task_type.strip():
            raise ValueError("Task type cannot be empty.")
        self._handlers[task_type] = handler
        logger.info(f"Registered job handler for task_type: {task_type}")

    def get_handler(self, task_type: str) -> JobHandler | None:
        return self._handlers.get(task_type)

    async def dispatch(self, job: Job) -> JobResult:
        handler = self.get_handler(job.task_type)
        if not handler:
            error_msg = f"No handler registered for task_type: '{job.task_type}'"
            logger.error(error_msg)
            return JobResult(success=False, error=error_msg, retryable=False)

        try:
            return await handler.handle(job)
        except Exception as e:
            logger.exception(
                f"Unhandled exception during job {job.job_id} ({job.task_type}): {e}"
            )
            return JobResult(success=False, error=str(e), retryable=True)


class DurableTaskQueue(ABC):
    """Abstract interface for durable task queue providers."""

    @abstractmethod
    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
        correlation_id: str | None = None,
    ) -> Job:
        """Enqueues a durable job and returns the created Job object."""
        pass

    @abstractmethod
    async def acknowledge(self, job_id: UUID) -> None:
        """Acknowledges successful processing of a job."""
        pass

    @abstractmethod
    async def reject(self, job_id: UUID, error: str, retryable: bool = True) -> None:
        """Rejects a job, triggering retry with backoff or dead-letter routing."""
        pass
