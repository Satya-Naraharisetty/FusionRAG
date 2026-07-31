import logging
from app.chat.domain.models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    ConversationContext,
    RetrievalDiagnostics,
)
from app.documents.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)


class ConversationContextBuilder:
    def build_context(
        self,
        conversation: Conversation,
        recent_messages: list[ConversationMessage],
        summary: ConversationSummary | None,
        retrieved_chunks: list[RetrievedChunk],
        diagnostics: RetrievalDiagnostics,
    ) -> ConversationContext:
        """
        Build the ConversationContext DTO with static type checking to eliminate Any signatures.
        """
        return ConversationContext(
            conversation=conversation,
            recent_messages=recent_messages,
            summary=summary,
            retrieved_chunks=retrieved_chunks,
            diagnostics=diagnostics,
        )
