from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any
from uuid import UUID


class DomainEvent:
    """Base class for all domain events."""

    pass


class DocumentProcessingCompleted(DomainEvent):
    """
    Event dispatched when a document is fully processed, text extracted, and chunked.
    """

    def __init__(self, document_id: UUID, user_id: UUID) -> None:
        self.document_id = document_id
        self.user_id = user_id


class EventDispatcher(ABC):
    """
    Interface for dispatching domain events to registered handlers synchronously.
    """

    @abstractmethod
    def dispatch(self, event: DomainEvent) -> None:
        """
        Dispatches a domain event to all registered listeners.
        """
        pass

    @abstractmethod
    def register(
        self, event_type: type[DomainEvent], handler: Callable[[Any], None]
    ) -> None:
        """
        Registers a handler function for a specific event type.
        """
        pass
