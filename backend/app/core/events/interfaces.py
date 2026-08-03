from abc import ABC, abstractmethod
from typing import Any, Callable, Type

from pydantic import BaseModel


class BaseEvent(BaseModel):
    """Base class for all system events."""
    pass


class DomainEvent(BaseEvent):
    """Base class for thread-safe in-process domain events."""
    pass


class IntegrationEvent(BaseEvent):
    """Base class for cross-boundary distributed integration events."""
    pass


class BaseEventBus(ABC):
    @abstractmethod
    async def publish(self, event: IntegrationEvent) -> None:
        """Publish an integration event to the message broker."""
        pass

    @abstractmethod
    async def subscribe(self, event_type: Type[IntegrationEvent], handler: Callable[[Any], Any]) -> None:
        """Subscribe a background worker to an integration event stream."""
        pass


class BaseDomainEventDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, event: DomainEvent) -> None:
        """Dispatch a domain event in-process to registered handlers."""
        pass

    @abstractmethod
    def register(self, event_type: Type[DomainEvent], handler: Callable[[Any], Any]) -> None:
        """Register an in-process handler for a domain event."""
        pass
