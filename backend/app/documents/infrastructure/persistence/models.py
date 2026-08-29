import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SQLAlchemyProcessingConfigVersion(Base):
    __tablename__ = "processing_config_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    config_identifier: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    config_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SQLAlchemyDocument(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_id_scope", "user_id", "scope"),
        Index("ix_documents_user_id_conversation_id", "user_id", "conversation_id"),
        UniqueConstraint("user_id", "id", name="uq_documents_user_id_id"),
        UniqueConstraint("user_id", "checksum", name="uq_documents_user_checksum"),
        CheckConstraint(
            "active_version >= 0", name="ck_documents_active_version_nonneg"
        ),
        CheckConstraint(
            "version >= active_version", name="ck_documents_version_ge_active"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(
        String(50), default="LIBRARY", server_default="LIBRARY", nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), nullable=False
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    active_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    active_processing_config_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_config_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    extractor_version: Mapped[str] = mapped_column(
        String(20), default="v1", nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    chunks: Mapped[list["SQLAlchemyChunk"]] = relationship(
        "SQLAlchemyChunk", back_populates="document", cascade="all, delete-orphan"
    )
    elements: Mapped[list["SQLAlchemyDocumentElement"]] = relationship(
        "SQLAlchemyDocumentElement",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class SQLAlchemyDocumentProcessingRun(Base):
    __tablename__ = "document_processing_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            name="uq_processing_runs_user_doc_ver",
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_processing_runs_doc_active",
            "document_id",
            unique=True,
            postgresql_where=text("state = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_config_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_config_versions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(50), default="PROCESSING", nullable=False)
    validation_gate_passed: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SQLAlchemyDocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "job_type", name="uq_processing_jobs_run_job_type"),
        UniqueConstraint("idempotency_key", name="uq_processing_jobs_idempotency_key"),
        ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_processing_runs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SQLAlchemyDocumentElement(Base):
    __tablename__ = "document_elements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            "id",
            name="uq_document_elements_composite_id",
        ),
        UniqueConstraint(
            "document_id",
            "document_version",
            "element_index",
            name="uq_document_elements_doc_ver_idx",
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    element_index: Mapped[int] = mapped_column(Integer, nullable=False)
    element_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_element_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounding_box_json: Mapped[dict | None] = mapped_column(
        "bounding_box", JSON, nullable=True
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        server_default=FetchedValue(),
        nullable=True,
    )

    # Relationships
    document: Mapped["SQLAlchemyDocument"] = relationship(
        "SQLAlchemyDocument", back_populates="elements"
    )


class SQLAlchemyGraphEntity(Base):
    __tablename__ = "graph_entities"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_name",
            "normalized_type",
            name="uq_graph_entities_user_norm_name_type",
        ),
        UniqueConstraint("user_id", "id", name="uq_graph_entities_user_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties_json: Mapped[dict] = mapped_column(
        "properties", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SQLAlchemyGraphRelationship(Base):
    __tablename__ = "graph_relationships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_entity_id",
            "normalized_relation_type",
            "target_entity_id",
            name="uq_graph_canonical_relationship",
        ),
        UniqueConstraint("user_id", "id", name="uq_graph_relationships_user_id_id"),
        CheckConstraint(
            "source_entity_id <> target_entity_id", name="ck_graph_no_self_loops"
        ),
        ForeignKeyConstraint(
            ["user_id", "source_entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "target_entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_relation_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SQLAlchemyRelationshipEvidence(Base):
    __tablename__ = "graph_relationship_evidence"
    __table_args__ = (
        UniqueConstraint(
            "relationship_id",
            "document_id",
            "document_version",
            "source_element_id",
            name="uq_relationship_evidence_provenance",
        ),
        ForeignKeyConstraint(
            ["user_id", "relationship_id"],
            ["graph_relationships.user_id", "graph_relationships.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id", "document_version", "source_element_id"],
            [
                "document_elements.user_id",
                "document_elements.document_id",
                "document_elements.document_version",
                "document_elements.id",
            ],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_element_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    source_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SQLAlchemyEntityMention(Base):
    __tablename__ = "graph_entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "document_id",
            "document_version",
            "element_id",
            name="uq_entity_mention_provenance",
        ),
        ForeignKeyConstraint(
            ["user_id", "entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id", "document_version", "element_id"],
            [
                "document_elements.user_id",
                "document_elements.document_id",
                "document_elements.document_version",
                "document_elements.id",
            ],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    element_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    source_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SQLAlchemyOutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            "event_type",
            name="uq_outbox_event_idempotency",
        ),
        ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        "payload", JSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SQLAlchemyChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    character_start: Mapped[int] = mapped_column(Integer, nullable=False)
    character_end: Mapped[int] = mapped_column(Integer, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        server_default=FetchedValue(),
        nullable=True,
    )

    # Relationships
    document: Mapped["SQLAlchemyDocument"] = relationship(
        "SQLAlchemyDocument", back_populates="chunks"
    )

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )


from sqlalchemy import DDL, event  # noqa: E402

event.listen(
    SQLAlchemyChunk.__table__,
    "after_create",
    DDL(
        "ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector;\n"
        "ALTER TABLE document_chunks ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;\n"
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_search_vector "
        "ON document_chunks USING gin (search_vector);"
    ).execute_if(dialect="postgresql"),
)

event.listen(
    SQLAlchemyDocumentElement.__table__,
    "after_create",
    DDL(
        "ALTER TABLE document_elements DROP COLUMN IF EXISTS search_vector;\n"
        "ALTER TABLE document_elements ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(normalized_content, ''))) STORED;\n"
        "CREATE INDEX IF NOT EXISTS ix_document_elements_search_vector "
        "ON document_elements USING gin (search_vector);"
    ).execute_if(dialect="postgresql"),
)


class SQLAlchemyEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    embedding_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    chunk: Mapped["SQLAlchemyChunk"] = relationship("SQLAlchemyChunk")


class SQLAlchemyDocumentFile(Base):
    __tablename__ = "document_files"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class SQLAlchemyCleanupJob(Base):
    __tablename__ = "durable_cleanup_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", name="uq_cleanup_resource"),
    )
