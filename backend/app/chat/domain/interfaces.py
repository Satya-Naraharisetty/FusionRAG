from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.chat.domain.agents import ToolCall, ToolDefinition
from app.chat.domain.models import (
    ChatMessage,
    Conversation,
    ConversationMessage,
    ConversationSummary,
    HistoryRewriteResult,
    MessageRole,
    Usage,
)


class TokenEstimator(ABC):
    @abstractmethod
    def estimate(self, text: str) -> int:
        """
        Estimate the number of tokens in the given text.
        """
        pass


class ProviderResponse(tuple):
    def __new__(
        cls, content: str | None, usage: Usage, tool_calls: list[ToolCall] | None = None
    ):
        return super().__new__(cls, (content or "", usage))

    def __init__(
        self,
        content: str | None,
        usage: Usage,
        tool_calls: list[ToolCall] | None = None,
    ):
        self.content = content or ""
        self.usage = usage
        self.tool_calls = tool_calls or []


class StreamChunk(tuple):
    def __new__(
        cls,
        text_delta: str,
        usage: Usage | None = None,
        tool_calls: list[ToolCall] | None = None,
    ):
        return super().__new__(cls, (text_delta, usage))

    def __init__(
        self,
        text_delta: str,
        usage: Usage | None = None,
        tool_calls: list[ToolCall] | None = None,
    ):
        self.text_delta = text_delta
        self.usage = usage
        self.tool_calls = tool_calls or []


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> ProviderResponse:
        """
        Generate a response from the LLM, optionally utilizing tool calling.
        """
        pass

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream the LLM response, yielding text chunks and tool calls.
        """
        pass


class ConversationRepository(ABC):
    @abstractmethod
    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Create a new conversation session."""
        pass

    @abstractmethod
    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Retrieve a conversation by its ID."""
        pass

    @abstractmethod
    async def list_conversations(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[Conversation]:
        """List conversations belonging to a user with pagination."""
        pass

    @abstractmethod
    async def update_conversation(self, conversation: Conversation) -> Conversation:
        """Update a conversation's details, enforcing optimistic locking version checks."""
        pass

    @abstractmethod
    async def delete_conversation(self, conversation_id: UUID) -> None:
        """Soft-deletes a conversation session."""
        pass


class MessageRepository(ABC):
    @abstractmethod
    async def add_message(self, message: ConversationMessage) -> ConversationMessage:
        """Persist a conversation message."""
        pass

    @abstractmethod
    async def get_recent_messages(
        self, conversation_id: UUID, limit: int, offset: int = 0
    ) -> list[ConversationMessage]:
        """Retrieve the recent messages for a conversation with pagination."""
        pass

    @abstractmethod
    async def count_messages(self, conversation_id: UUID) -> int:
        """Get the total message count of a conversation."""
        pass

    @abstractmethod
    async def create_assistant_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        role: MessageRole,
        content: str = "",
    ) -> ConversationMessage:
        """Initialize an assistant response in PENDING status."""
        pass

    @abstractmethod
    async def append_stream_chunk(self, message_id: UUID, content_chunk: str) -> None:
        """Append streamed text chunks to an assistant message."""
        pass

    @abstractmethod
    async def complete_message(
        self,
        message_id: UUID,
        prompt_tokens: int,
        completion_tokens: int,
        citations: list[dict[str, Any]] | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        """
        Transition an assistant message to COMPLETED status and set tokens & citations.

        ``content`` is applied only when provided (the streaming path already
        accumulated the answer via append_stream_chunk; the synchronous path
        needs it here).
        """
        pass

    @abstractmethod
    async def fail_message(
        self, message_id: UUID, error_message: str | None = None
    ) -> ConversationMessage:
        """Transition a message to FAILED status and attach error metadata."""
        pass

    @abstractmethod
    async def interrupt_message(
        self, message_id: UUID, reason: str | None = None
    ) -> ConversationMessage:
        """
        Transition an in-progress message (PENDING/STREAMING) to INTERRUPTED.

        Used when a streaming client disconnects mid-generation so partial
        content is persisted in a terminal state. No-op for messages that are
        already in a terminal status (COMPLETED/FAILED/INTERRUPTED).
        """
        pass


class SummaryRepository(ABC):
    @abstractmethod
    async def save_summary(self, summary: ConversationSummary) -> ConversationSummary:
        """Persist a conversation summary."""
        pass

    @abstractmethod
    async def latest_summary(self, conversation_id: UUID) -> ConversationSummary | None:
        """Retrieve the latest summary for a conversation."""
        pass


class ConversationMemory(ABC):
    @abstractmethod
    async def load_memory(
        self, conversation_id: UUID
    ) -> tuple[list[ConversationMessage], ConversationSummary | None]:
        """Retrieve active memory (the latest summary plus messages created after it)."""
        pass


class HistoryRewriter(ABC):
    @abstractmethod
    async def rewrite(
        self, question: str, history: list[ConversationMessage]
    ) -> HistoryRewriteResult:
        """Rewrite follow-up question to standalone form based on conversational context."""
        pass


class ConversationSummarizer(ABC):
    @abstractmethod
    async def summarize(
        self, conversation_id: UUID, up_to_message_id: UUID
    ) -> ConversationSummary:
        """Summarize conversation history up to a specific message ID."""
        pass


class ConversationTitleGenerator(ABC):
    @abstractmethod
    async def generate_title(
        self, first_user_message: str, assistant_answer: str | None = None
    ) -> str:
        """Generate a title based on the first turn of conversation."""
        pass


class HistoryRewriteCache(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Retrieve a cached rewritten query."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store a rewritten query with a TTL."""
        pass
