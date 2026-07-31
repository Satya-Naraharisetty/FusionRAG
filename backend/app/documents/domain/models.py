from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    def transition_to(self, target: DocumentStatus) -> None:
        DocumentStateMachine.validate_transition(self.status, target)
        self.status = target


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
        EmbeddingStatus.FAILED: [EmbeddingStatus.PENDING],
        EmbeddingStatus.COMPLETED: [EmbeddingStatus.PENDING],
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
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_index: int

    model_config = ConfigDict(frozen=True)


class SearchResult(BaseModel):
    original_query: str
    retrieval_time: float
    total_matches: int
    retrieved_chunks: list[RetrievedChunk]
    search_strategy: str = "semantic"

