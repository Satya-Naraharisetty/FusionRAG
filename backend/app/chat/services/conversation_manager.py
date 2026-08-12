import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from app.chat.domain.events import ConversationCreated, ConversationMessageCreated
from app.chat.domain.exceptions import ConversationNotFoundException
from app.chat.domain.interfaces import (
    ConversationMemory,
    ConversationRepository,
    ConversationTitleGenerator,
    HistoryRewriter,
    MessageRepository,
    SummaryRepository,
)
from app.chat.domain.models import (
    Conversation,
    ConversationContext,
    ConversationMessage,
    ConversationSettings,
    HistoryRewriteResult,
    MessageRole,
    MessageStatus,
)
from app.chat.services.access_service import ConversationAccessService
from app.documents.domain.events import EventDispatcher
from app.documents.services.document_service import DocumentService

logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        summary_repo: SummaryRepository,
        access_service: ConversationAccessService,
        memory: ConversationMemory,
        rewriter: HistoryRewriter,
        title_generator: ConversationTitleGenerator,
        event_dispatcher: EventDispatcher,
        document_service: DocumentService | None = None,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._access_service = access_service
        self._memory = memory
        self._rewriter = rewriter
        self._title_generator = title_generator
        self._event_dispatcher = event_dispatcher
        self._document_service = document_service

    async def get_or_create_conversation(
        self,
        conversation_id: UUID | None,
        user_id: UUID,
        settings: ConversationSettings | None = None,
    ) -> Conversation:
        """
        Retrieves an existing conversation (verifying ownership) or creates a new one.
        """
        if conversation_id:
            await self._access_service.verify_owner(conversation_id, user_id)
            conversation = await self._conversation_repo.get_conversation(
                conversation_id
            )
            if not conversation:
                raise ConversationNotFoundException(
                    f"Conversation {conversation_id} not found."
                )
            return conversation

        # Create new conversation
        now = datetime.now(UTC)
        new_conv = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title="New Conversation",
            settings=settings or ConversationSettings(),
            version=1,
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        saved_conv = await self._conversation_repo.create_conversation(new_conv)
        self._event_dispatcher.dispatch(ConversationCreated(saved_conv.id, user_id))
        return saved_conv

    async def prepare_context(
        self,
        conversation_id: UUID,
        user_id: UUID,
        question: str,
        skip_rewrite: bool = False,
    ) -> tuple[ConversationContext, HistoryRewriteResult]:
        """
        Orchestrates memory loading and query rewriting, saves the incoming user message,
        and returns the ConversationContext before generating assistant responses.

        When ``skip_rewrite`` is True (e.g. the user has no uploaded documents
        to retrieve from), the LLM query-rewrite call is skipped and the
        original question is used as-is — the rewrite only exists to improve
        retrieval, so the extra LLM call would be wasted.
        """
        # 1. Ownership validation
        await self._access_service.verify_owner(conversation_id, user_id)

        # 2. Load memory (recent messages + summary) before appending new question
        recent_messages, summary = await self._memory.load_memory(conversation_id)

        # 3. Rewrite follow-up question
        if skip_rewrite:
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="No documents uploaded; query rewrite skipped.",
                rewrite_applied=False,
            )
        else:
            rewrite_result = await self._rewriter.rewrite(question, recent_messages)

        # 4. Save user message to database
        user_message = ConversationMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            status=MessageStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        await self._message_repo.add_message(user_message)

        # 5. Update last_message_at and message count in conversation details
        conversation = await self._conversation_repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundException(
                f"Conversation {conversation_id} not found."
            )
        conversation.last_message_at = datetime.now(UTC)
        conversation.metadata.message_count = await self._message_repo.count_messages(
            conversation_id
        )
        await self._conversation_repo.update_conversation(conversation)

        # Build Context containing loaded memory
        context = ConversationContext(
            conversation=conversation,
            recent_messages=recent_messages,
            summary=summary,
        )

        return context, rewrite_result

    async def finalize_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        assistant_content: str,
        prompt_tokens: int,
        completion_tokens: int,
        citations: list[dict] | None = None,
    ) -> None:
        """
        Completes the assistant's message in the DB and dispatches domain events to trigger background summarization.
        Auto-generates the conversation title if this is the first turn.
        """
        # 1. Complete the message in database. Content is applied here for the
        # synchronous path; the streaming path already accumulated it via
        # append_stream_chunk (and passing the same value is idempotent).
        await self._message_repo.complete_message(
            message_id=message_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            citations=citations,
            content=assistant_content,
        )

        # 2. Check if we need to auto-generate the title (if conversation only has first user + assistant messages)
        conversation = await self._conversation_repo.get_conversation(conversation_id)
        if conversation and conversation.title == "New Conversation":
            # Check message count
            count = await self._message_repo.count_messages(conversation_id)
            if count == 2:
                # Retrieve the messages
                messages = await self._message_repo.get_recent_messages(
                    conversation_id, limit=2
                )
                user_msg = next(
                    (m.content for m in messages if m.role == MessageRole.USER), None
                )
                if user_msg:
                    new_title = await self._title_generator.generate_title(
                        first_user_message=user_msg,
                        assistant_answer=assistant_content,
                    )
                    conversation.title = new_title
                    conversation = await self._conversation_repo.update_conversation(
                        conversation
                    )

        # 3. Update last message metadata
        if conversation:
            conversation.metadata.last_model = conversation.settings.model
            conversation.metadata.last_provider = conversation.settings.provider
            conversation.metadata.last_tokens = prompt_tokens + completion_tokens
            conversation.metadata.message_count = (
                await self._message_repo.count_messages(conversation_id)
            )
            await self._conversation_repo.update_conversation(conversation)

        # 4. Dispatch domain event to handle background tasks (like summarization)
        self._event_dispatcher.dispatch(
            ConversationMessageCreated(
                conversation_id=conversation_id,
                message_id=message_id,
                message_role=MessageRole.ASSISTANT,
            )
        )

    async def delete_conversation(self, conversation_id: UUID, user_id: UUID) -> int:
        """
        Deletes a conversation and all associated documents.
        Returns the count of deleted documents.
        """
        # Verify ownership first
        await self._access_service.verify_owner(conversation_id, user_id)

        # Delete associated documents if document service is available
        deleted_docs_count = 0
        if self._document_service:
            try:
                deleted_docs_count = (
                    self._document_service.delete_documents_by_conversation(
                        conversation_id, user_id
                    )
                )
                logger.info(
                    f"Deleted {deleted_docs_count} documents for conversation {conversation_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to delete documents for conversation {conversation_id}: {e}"
                )

        # Delete the conversation (soft delete)
        await self._conversation_repo.delete_conversation(conversation_id)

        return deleted_docs_count
