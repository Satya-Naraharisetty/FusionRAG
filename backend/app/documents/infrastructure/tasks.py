from collections.abc import Callable
from typing import Any

from app.documents.domain.interfaces import TaskQueue
from fastapi import BackgroundTasks


class FastAPIBackgroundTasksQueue(TaskQueue):
    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """
        Enqueues a task onto FastAPI's in-process background worker.
        """
        self._background_tasks.add_task(func, *args, **kwargs)


class SyncTaskQueue(TaskQueue):
    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """
        Executes task immediately and synchronously (for test isolation).
        """
        func(*args, **kwargs)
