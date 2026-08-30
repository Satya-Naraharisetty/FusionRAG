import hashlib
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid5

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
    version: int = 0
    active_version: int = 0
    active_processing_config_version_id: UUID | None = None
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
        EmbeddingStatus.COMPLETED: [
            EmbeddingStatus.PENDING,
            EmbeddingStatus.GENERATING,
        ],
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


# =====================================================================
# Multimodal, Structured & Knowledge Graph Document Domain Models
# =====================================================================

NAMESPACE_fusion_rag = UUID("e89f8742-1234-5678-9abc-def012345678")


def normalize_entity_name(raw_name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", raw_name).strip().casefold().split())


def normalize_entity_type(raw_type: str) -> str:
    return unicodedata.normalize("NFKC", raw_type).strip().upper()


def format_visual_embedding_payload(
    element_type: str, caption: str, visual_description: str, extracted_data: str = ""
) -> str:
    parts = [
        f"Type: {element_type}",
        f"Caption: {caption.strip()}",
        f"Description: {visual_description.strip()}",
    ]
    if extracted_data.strip():
        parts.append(f"Data: {extracted_data.strip()}")
    return "\n".join(parts)


def sanitize_cell_value(raw: str) -> tuple[Decimal | None, str]:
    if raw.startswith(("\t", "\r")):
        return None, f"'{raw}"
    trimmed = raw.strip()
    if not trimmed:
        return None, ""
    cleaned_num = trimmed.replace(",", "")
    if cleaned_num.startswith(("-", "+")) or (cleaned_num and cleaned_num[0].isdigit()):
        try:
            val = Decimal(cleaned_num)
            return val, trimmed
        except InvalidOperation:
            pass
    if any(trimmed.startswith(prefix) for prefix in ("=", "+", "-", "@")):
        return None, f"'{trimmed}"
    return None, trimmed


def generate_element_id(
    user_id: UUID, document_id: UUID, document_version: int, element_index: int
) -> UUID:

    return uuid5(
        NAMESPACE_fusion_rag,
        f"{user_id}:{document_id}:{document_version}:element:{element_index}",
    )


def generate_entity_id(
    user_id: UUID, normalized_entity_name: str, normalized_entity_type: str
) -> UUID:

    return uuid5(
        NAMESPACE_fusion_rag,
        f"{user_id}:entity:{normalized_entity_name}:{normalized_entity_type}",
    )


def generate_qdrant_point_id(
    user_id: UUID,
    document_id: UUID,
    document_version: int,
    element_id: UUID,
    representation_type: str,
    embedding_contract_id: str,
) -> UUID:

    return uuid5(
        NAMESPACE_fusion_rag,
        f"{user_id}:{document_id}:{document_version}:{element_id}:{representation_type}:{embedding_contract_id}",
    )


class ElementType(str, Enum):
    TEXT = "TEXT"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    CHART = "CHART"


class ElementStatus(str, Enum):
    VALID = "VALID"
    ARCHIVED = "ARCHIVED"
    REVOKED = "REVOKED"


RepresentationType = Literal["TEXT", "VISUAL_SEMANTIC", "TABLE_SEMANTIC"]
CanonicalIdentity = tuple[
    UUID, int, UUID
]  # (document_id, document_version, element_id)


class DocumentElement(BaseModel):
    id: UUID
    user_id: UUID
    document_id: UUID
    document_version: int
    element_index: int
    element_type: ElementType
    parent_element_id: UUID | None = None
    content: str
    normalized_content: str
    page_number: int | None = None
    bounding_box: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ElementStatus = ElementStatus.VALID
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class TableCell(BaseModel):
    row_index: int
    col_index: int
    raw_value: str
    sanitized_value: str
    numeric_value: Decimal | None = None
    row_span: int = 1
    col_span: int = 1


class TableDimension(BaseModel):
    row_count: int
    col_count: int


class StructuredTable(BaseModel):
    element_id: UUID
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    dimensions: TableDimension
    cells: list[TableCell] = Field(default_factory=list)
    summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GraphEntity(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    normalized_name: str
    entity_type: str
    normalized_type: str
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class EntityMention(BaseModel):
    id: UUID
    user_id: UUID
    entity_id: UUID
    document_id: UUID
    document_version: int
    element_id: UUID
    confidence: float = 1.0
    status: ElementStatus = ElementStatus.VALID
    source_span: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class GraphRelationship(BaseModel):
    id: UUID
    user_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str
    normalized_relation_type: str
    weight: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class RelationshipEvidence(BaseModel):
    id: UUID
    user_id: UUID
    relationship_id: UUID
    document_id: UUID
    document_version: int
    source_element_id: UUID
    confidence: float = 1.0
    status: ElementStatus = ElementStatus.VALID
    source_span: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class ProcessingRunState(str, Enum):
    PROCESSING = "PROCESSING"
    VALIDATING = "VALIDATING"
    READY_FOR_CUTOVER = "READY_FOR_CUTOVER"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    CLEANED = "CLEANED"
    FAILED = "FAILED"


class ProcessingJobStatus(str, Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProcessingRun(BaseModel):
    id: UUID
    user_id: UUID
    document_id: UUID
    document_version: int
    processing_config_version_id: UUID
    state: ProcessingRunState
    validation_gate_passed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    superseded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProcessingJob(BaseModel):
    id: UUID
    run_id: UUID
    user_id: UUID
    document_id: UUID
    document_version: int
    job_type: str
    idempotency_key: str
    status: ProcessingJobStatus
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceType(str, Enum):
    TEXT_CHUNK = "TEXT_CHUNK"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    CHART = "CHART"
    GRAPH_RELATIONSHIP = "GRAPH_RELATIONSHIP"
    ENTITY_MENTION = "ENTITY_MENTION"


class EvidenceItem(BaseModel):
    evidence_id: UUID
    evidence_type: EvidenceType
    user_id: UUID
    document_id: UUID
    document_version: int
    element_id: UUID
    content: str
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ExpectedVectorIdentity(BaseModel):
    user_id: UUID
    document_id: UUID
    document_version: int
    element_id: UUID
    representation_type: str
    embedding_contract_id: str


class ExpectedArtifactManifest(BaseModel):
    manifest_id: UUID
    document_id: UUID
    document_version: int
    expected_element_ids: list[UUID] = Field(default_factory=list)
    expected_vector_identities: list[ExpectedVectorIdentity] = Field(
        default_factory=list
    )
    embedding_contract_id: str


class ProcessingConfigVersion(BaseModel):
    extraction_provider: str = "gemini"
    extraction_model: str = "gemini-3.5-flash"
    extraction_model_revision: str = "v1"
    extraction_schema_revision: str = "v1"
    normalization_revision: str = "v1"
    chunking_revision: str = "v1"
    embedding_provider: str = "jina"
    embedding_model: str = "jina-embeddings-v3"
    embedding_model_revision: str = "v1"
    embedding_dimensions: int = 768
    prompt_revision: str = "v1"
    vision_prompt_revision: str = "v1"
    ocr_config_revision: str = "v1"
    table_parser_revision: str = "v1"
    graph_extraction_prompt_revision: str = "v1"
    citation_validator_provider: str = "gemini"
    citation_validator_model: str = "gemini-3.5-flash"
    citation_validator_model_revision: str = "v1"
    citation_validator_policy_revision: str = "v1"
    entailment_threshold: float = 0.85
    contradiction_threshold: float = 0.50
    citation_timeout_seconds: int = 2

    @property
    def config_identifier(self) -> str:
        canonical_json = json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def get_embedding_contract_id(self, representation_type: str = "TEXT") -> str:
        contract_payload = {
            "representation_type": representation_type,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_model_revision": self.embedding_model_revision,
            "embedding_dimensions": self.embedding_dimensions,
            "normalization_revision": self.normalization_revision,
            "chunking_revision": self.chunking_revision,
            "prompt_revision": self.prompt_revision,
            "vision_prompt_revision": self.vision_prompt_revision,
            "ocr_config_revision": self.ocr_config_revision,
            "table_parser_revision": self.table_parser_revision,
        }
        canonical_json = json.dumps(
            contract_payload, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class AuthorizedDocumentVersion(BaseModel):
    active_version: int
    active_config_id: UUID
    active_embedding_contract_id: str

    model_config = ConfigDict(frozen=True)


class AuthorizedDocumentScope(BaseModel):
    user_id: UUID
    authorized_docs: dict[UUID, AuthorizedDocumentVersion] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class PlanAttempt(BaseModel):
    attempt_index: int
    plan_dag: Any
    execution_results: dict[UUID, Any] = Field(default_factory=dict)
    evaluation_result: Any | None = None
