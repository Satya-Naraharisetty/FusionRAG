from uuid import UUID

from app.chat.domain.exceptions import (
    ConversationNotFoundException,
    UnauthorizedConversationAccessException,
)
from app.chat.domain.interfaces import ConversationRepository


class ConversationAccessService:
    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self._conversation_repo = conversation_repo

    async def verify_owner(self, conversation_id: UUID, user_id: UUID) -> None:
        """
        Verify that a conversation exists and belongs to the specified user.
        Raises ConversationNotFoundException or UnauthorizedConversationAccessException.
        """
        conversation = await self._conversation_repo.get_conversation(conversation_id)
        if not conversation:
            raise ConversationNotFoundException(f"Conversation {conversation_id} was not found.")

        if conversation.user_id != user_id:
            raise UnauthorizedConversationAccessException(
                f"User {user_id} is not authorized to access conversation {conversation_id}."
            )
