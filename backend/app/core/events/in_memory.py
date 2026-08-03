import asyncio
import logging
from typing import Any, Callable, Dict, List, Type

from app.core.events.interfaces import BaseDomainEventDispatcher, DomainEvent

logger = logging.getLogger(__name__)


class InMemoryDomainEventDispatcher(BaseDomainEventDispatcher):
    def __init__(self) -> None:
        self._handlers: Dict[Type[DomainEvent], List[Callable[[Any], Any]]] = {}

    def register(self, event_type: Type[DomainEvent], handler: Callable[[Any], Any]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def dispatch(self, event: DomainEvent) -> None:
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        tasks = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"Error in domain event handler {handler.__name__} for event {event_type.__name__}: {e}"
                )

        if tasks:
            # Run all async handlers concurrently
            await asyncio.gather(*tasks, return_exceptions=True)
