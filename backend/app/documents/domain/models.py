import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentScope(str, Enum):
    LIBRARY = "LIBRARY"
    CONVERSATION = "CONVERSATION"


class DocumentStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentStateMachine:
    _transitions: dict[DocumentStatus, list[DocumentStatus]] = {
        DocumentStatus.QUEUED: [DocumentStatus.PROCESSING],
        DocumentStatus.PROCESSING: [DocumentStatus.COMPLETED, DocumentStatus.FAILED],
        DocumentStatus.FAILED: [DocumentStatus.QUEUED],
        DocumentStatus.COMPLETED: [DocumentStatus.QUEUED],
    }

    @classmethod
    def validate_transition(
        cls, current: DocumentStatus, target: DocumentStatus
    ) -> None:
        if current == target:
            return
        allowed = cls._transitions.get(current, [])
        if target not in allowed:
            from app.documents.domain.exceptions import InvalidStateTransitionException

            raise InvalidStateTransitionException(
                f"Invalid transition from {current.value} to {target.value}"
            )


class DocumentMetadata(BaseModel):
    page_count: int | None = None
    word_count: int | None = None
    language: str | None = None


class Document(BaseModel):
    id: UUID
    user_id: UUID
    scope: DocumentScope = DocumentScope.LIBRARY
    conversation_id: UUID | None = None
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    checksum: str
    status: DocumentStatus
    extractor_version: str = "v1"
    failure_reason: str | None = None
    page_count: int | None = None
    word_count: int | None = None
    language: str | None = None
    created_at: datetime
    updated_at: datetime
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_scope_invariants(self) -> "Document":
        if self.scope == DocumentScope.LIBRARY:
            if self.conversation_id is not None:
                raise ValueError(
                    "Library-scoped documents must not have a conversation_id."
                )
        elif self.scope == DocumentScope.CONVERSATION:
            if self.conversation_id is None:
                raise ValueError(
                    "Conversation-scoped documents must have a conversation_id."
                )
        return self

    def transition_to(self, target: DocumentStatus) -> None:
        DocumentStateMachine.validate_transition(self.status, target)
        self.status = target


class DocumentScopeIntent(BaseModel):
    cleaned_query: str
    include_library_documents: bool


class DocumentScopeIntentParser:
    _PATTERN = re.compile(r"(?<!\w)@documents\b", re.IGNORECASE)

    @classmethod
    def parse(cls, query: str) -> DocumentScopeIntent:
        has_mention = bool(cls._PATTERN.search(query))
        cleaned = cls._PATTERN.sub(" ", query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            cleaned = query
        return DocumentScopeIntent(
            cleaned_query=cleaned,
            include_library_documents=has_mention,
        )


class DocumentRetrievalScope(BaseModel):
    user_id: UUID
    conversation_id: UUID | None = None
    include_conversation_documents: bool = False
    include_library_documents: bool = False
    document_ids: list[UUID] | None = None
    tags: list[str] | None = None
    filter_metadata: dict[str, Any] | None = None


class Chunk(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    character_start: int
    character_end: int
    token_estimate: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionResult(BaseModel):
    text: str
    page_count: int | None = None


class ChunkResult(BaseModel):
    chunks: list[Chunk]


class EmbeddingStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EmbeddingStateMachine:
    _transitions: dict[EmbeddingStatus, list[EmbeddingStatus]] = {
        EmbeddingStatus.PENDING: [EmbeddingStatus.GENERATING],
        EmbeddingStatus.GENERATING: [EmbeddingStatus.COMPLETED, EmbeddingStatus.FAILED],
        EmbeddingStatus.FAILED: [EmbeddingStatus.PENDING, EmbeddingStatus.GENERATING],
        EmbeddingStatus.COMPLETED: [EmbeddingStatus.PENDING, EmbeddingStatus.GENERATING],
    }

    @classmethod
    def validate_transition(
        cls, current: EmbeddingStatus, target: EmbeddingStatus
    ) -> None:
        if current == target:
            return
        allowed = cls._transitions.get(current, [])
        if target not in allowed:
            from app.documents.domain.exceptions import InvalidStateTransitionException

            raise InvalidStateTransitionException(
                f"Invalid embedding transition from {current.name} to {target.name}"
            )


class EmbeddingMetadata(BaseModel):
    provider: str
    model: str
    dimension: int
    embedding_version: str


class Embedding(BaseModel):
    id: UUID
    chunk_id: UUID
    status: EmbeddingStatus
    metadata: EmbeddingMetadata
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_name: str
    text: str
    similarity_score: float
    normalized_score: float | None = None
    rerank_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_index: int

    model_config = ConfigDict(frozen=True)


class RetrievalMode(str, Enum):
    SEMANTIC = "semantic"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    AUTO = "auto"


class FusionMethod(str, Enum):
    RRF = "RRF"


class RerankerName(str, Enum):
    IDENTITY = "IdentityReranker"
    SEMANTIC = "SemanticSearchRanker"
    JINA = "JinaReranker"
    JINA_CROSS_ENCODER = "JinaCrossEncoderReranker"
    MOCK = "MagicMock"


class QueryStats(BaseModel):
    original_length: int
    cleaned_length: int
    word_count: int
    char_count: int
    has_acronyms_expanded: bool
    has_typos_corrected: bool
    processing_time_ms: float
    expansions_count: int
    corrections_count: int


class ProcessedQuery(BaseModel):
    original_query: str
    cleaned_query: str
    expanded_query: str
    stats: QueryStats


class SearchResult(BaseModel):
    original_query: str
    retrieval_time: float
    total_matches: int
    retrieved_chunks: list[RetrievedChunk]
    search_strategy: str = "semantic"
    retrieval_strategy: RetrievalMode = RetrievalMode.SEMANTIC
    dense_matches: list[RetrievedChunk] | None = None
    sparse_matches: list[RetrievedChunk] | None = None
    fusion_method: FusionMethod | None = None
    reranker: RerankerName | None = None
    query_type: str | None = None
    expanded_queries: list[str] | None = None
    subtask_queries: list[str] | None = None
    diagnostics: dict[str, Any] | None = None


class CleanupJob(BaseModel):
    id: UUID
    resource_type: str
    resource_id: UUID
    payload: dict[str, Any]
    status: str
    attempts: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
