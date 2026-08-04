from uuid import UUID

from app.chat.domain.models import MessageRole
from app.documents.domain.events import DomainEvent


class ConversationCreated(DomainEvent):
    """Event dispatched when a conversation is successfully created."""

    def __init__(self, conversation_id: UUID, user_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id


class ConversationMessageCreated(DomainEvent):
    """Event dispatched when a message is added to a conversation."""

    def __init__(
        self, conversation_id: UUID, message_id: UUID, message_role: MessageRole
    ) -> None:
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.message_role = message_role


class ConversationSummarized(DomainEvent):
    """Event dispatched when a conversation generates a new summary."""

    def __init__(self, conversation_id: UUID, summary_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.summary_id = summary_id


class ConversationDeleted(DomainEvent):
    """Event dispatched when a conversation is soft deleted."""

    def __init__(self, conversation_id: UUID, user_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id
