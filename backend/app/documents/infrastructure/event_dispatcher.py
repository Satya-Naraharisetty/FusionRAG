from collections.abc import Callable
from typing import Any

from app.documents.domain.events import DomainEvent, EventDispatcher


class SimpleEventDispatcher(EventDispatcher):
    """
    A simple, synchronous, in-memory implementation of the EventDispatcher.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[[Any], None]]] = {}

    def register(
        self, event_type: type[DomainEvent], handler: Callable[[Any], None]
    ) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def dispatch(self, event: DomainEvent) -> None:
        event_type = type(event)
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                handler(event)
