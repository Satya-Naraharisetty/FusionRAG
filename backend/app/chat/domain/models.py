from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.documents.domain.models import RetrievalMode, RetrievedChunk


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"
    FUNCTION = "function"


class ChatMessage(BaseModel):
    role: ChatRole | MessageRole | str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Citation(BaseModel):
    document_id: UUID
    document_name: str
    chunk_id: UUID
    chunk_index: int
    url: str | None = None
    page_number: int | None = None
    line_number: int | None = None
    content: str | None = None
    element_type: str | None = None
    confidence: float | None = None
    entailment_status: str | None = None


class GroundedContext(BaseModel):
    concatenated_context: str
    chunk_references: list[RetrievedChunk]
    token_estimate: int


# --- Provider & Conversation Domain Models ---


class LLMProviderType(str, Enum):
    GEMINI = "gemini"


class ConversationState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"  # Soft-deleted status for retention service cleanup


class MessageStatus(str, Enum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # Client stopped the stream mid-generation; partial content preserved


class ConversationSettings(BaseModel):
    temperature: float = 0.0
    provider: LLMProviderType = LLMProviderType.GEMINI
    model: str = "gemini-3.5-flash-lite"

    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID
    stream: bool = False
    hybrid_enabled: bool = True
    system_prompt_version: str = "v1"


class ChatSession(BaseModel):
    conversation_id: UUID
    active_model: str
    active_provider: str
    system_prompt_version: str
    created_at: datetime


class ConversationMetadata(BaseModel):
    message_count: int = 0
    last_model: str | None = None
    last_provider: str | None = None
    last_tokens: int = 0
    last_cost: float = 0.0
    last_latency_ms: float = 0.0


class Conversation(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    state: ConversationState = ConversationState.ACTIVE
    settings: ConversationSettings = Field(default_factory=ConversationSettings)
    version: int = 1
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @property
    def chat_session(self) -> ChatSession:
        return ChatSession(
            conversation_id=self.id,
            active_model=self.settings.model,
            active_provider=self.settings.provider.value
            if isinstance(self.settings.provider, Enum)
            else str(self.settings.provider),
            system_prompt_version=self.settings.system_prompt_version,
            created_at=self.created_at,
        )


class ConversationMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus = MessageStatus.COMPLETED
    citations: list[dict[str, Any]] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None
    structured_content: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationSummary(BaseModel):
    id: UUID
    conversation_id: UUID
    summary: str
    summary_version: int = 1
    covered_from_message_id: UUID
    covered_until_message_id: UUID
    message_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetrievalDiagnostics(BaseModel):
    rewritten: bool = False
    # True when retrieval (and the query rewrite that only serves it) was
    # skipped entirely because the user has no uploaded documents — the answer
    # is generated from general knowledge. Lets the frontend surface a hint
    # like "Answering from general knowledge — no documents uploaded".
    retrieval_skipped: bool = False
    dense_count: int = 0
    sparse_count: int = 0
    fusion_count: int = 0
    rerank_count: int = 0
    latencies: dict[str, float] = Field(default_factory=dict)


class ConversationContext(BaseModel):
    conversation: Conversation
    recent_messages: list[ConversationMessage]
    summary: ConversationSummary | None = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    diagnostics: RetrievalDiagnostics = Field(default_factory=RetrievalDiagnostics)


class ContextAction(str, Enum):
    CONTINUE = "CONTINUE"  # Follow-up on same topic/entity
    REFINE = "REFINE"  # Narrowing or filtering previous topic (e.g. "and in India?")
    SWITCH = (
        "SWITCH"  # Explicit or detected shift to a new topic (clears prior context)
    )
    RESET = "RESET"  # Explicit reset instruction
    STANDALONE = (
        "STANDALONE"  # Self-contained query requiring no prior conversational context
    )


class SourceMode(str, Enum):
    DOCUMENT_ONLY = "DOCUMENT_ONLY"
    WEB_REQUIRED = "WEB_REQUIRED"
    HYBRID = "HYBRID"
    CALCULATION_ONLY = "CALCULATION_ONLY"
    DIRECT_ANSWER = "DIRECT_ANSWER"


class DomainContext(BaseModel):
    primary: str = "GENERAL"
    secondary: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class ChannelRetrievalQueries(BaseModel):
    document_query: str | None = None
    web_query: str | None = None
    graph_query: str | None = None


class KnownValue(BaseModel):
    value: float | str
    unit: str = ""
    currency: str | None = None
    source: str = "general"  # "document" | "web" | "calculation"
    confidence: float = 1.0


class ConversationTopicState(BaseModel):
    active_subject: str | None = None
    active_role: str | None = None
    active_location: str | None = None
    active_entities: list[str] = Field(default_factory=list)
    active_intent: str | None = None
    timeframe: str | None = None
    compensation_period: str | None = None
    currency: str | None = None
    known_values: dict[str, KnownValue] = Field(default_factory=dict)


class ContextResolution(BaseModel):
    original_query: str
    contextualized_query: str
    retrieval_queries: ChannelRetrievalQueries = Field(
        default_factory=ChannelRetrievalQueries
    )
    is_context_dependent: bool = False
    context_action: ContextAction = ContextAction.STANDALONE
    intent: str = "GENERAL_QUERY"
    source_mode: SourceMode = SourceMode.DOCUMENT_ONLY
    domain_context: DomainContext = Field(default_factory=DomainContext)
    active_subject: str | None = None
    active_role: str | None = None
    active_location: str | None = None
    active_entities: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    rewrite_reason: str | None = None


class HistoryRewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    rewrite_reason: str
    rewrite_applied: bool
    context_action: ContextAction = ContextAction.STANDALONE
    intent: str = "GENERAL_QUERY"
    source_mode: SourceMode = SourceMode.DOCUMENT_ONLY
    domain_context: DomainContext = Field(default_factory=DomainContext)
    retrieval_queries: ChannelRetrievalQueries = Field(
        default_factory=ChannelRetrievalQueries
    )
    resolution: ContextResolution | None = None
    topic_state: ConversationTopicState | None = None


# --- Backwards compatibility & Answer Response update ---


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval_time_ms: float
    generation_time_ms: float
    total_time_ms: float
    model: str
    usage: Usage
    conversation_id: UUID | None = None
    diagnostics: RetrievalDiagnostics | None = None
