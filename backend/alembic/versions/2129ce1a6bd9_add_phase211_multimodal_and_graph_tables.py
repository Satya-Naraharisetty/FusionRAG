"""add_phase211_multimodal_and_graph_tables

Revision ID: 2129ce1a6bd9
Revises: e5f6a7b8c9d0
Create Date: 2026-08-30 03:00:15.663998

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2129ce1a6bd9"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. First, create processing_config_versions table
    op.create_table(
        "processing_config_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("config_identifier", sa.String(length=64), nullable=False),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_processing_config_versions_config_identifier"),
        "processing_config_versions",
        ["config_identifier"],
        unique=True,
    )

    # 2. Update documents table with new columns and unique constraints (needed for child composite FKs)
    op.add_column(
        "documents",
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("active_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("active_processing_config_version_id", sa.Uuid(), nullable=True),
    )
    op.alter_column(
        "documents",
        "file_size",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_documents_user_id_id", "documents", ["user_id", "id"]
    )
    op.create_unique_constraint(
        "uq_documents_user_checksum", "documents", ["user_id", "checksum"]
    )
    op.create_check_constraint(
        "ck_documents_active_version_nonneg", "documents", "active_version >= 0"
    )
    op.create_check_constraint(
        "ck_documents_version_ge_active", "documents", "version >= active_version"
    )
    op.create_foreign_key(
        "fk_documents_processing_config_version",
        "documents",
        "processing_config_versions",
        ["active_processing_config_version_id"],
        ["id"],
    )

    # 3. Create graph_entities table
    op.create_table(
        "graph_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("normalized_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "id", name="uq_graph_entities_user_id_id"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            "normalized_type",
            name="uq_graph_entities_user_norm_name_type",
        ),
    )
    op.create_index(
        op.f("ix_graph_entities_normalized_name"),
        "graph_entities",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_graph_entities_normalized_type"),
        "graph_entities",
        ["normalized_type"],
        unique=False,
    )

    # 4. Create graph_relationships table
    op.create_table(
        "graph_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_entity_id", sa.Uuid(), nullable=False),
        sa.Column("target_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=100), nullable=False),
        sa.Column("normalized_relation_type", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_entity_id <> target_entity_id", name="ck_graph_no_self_loops"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "source_entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "target_entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "id", name="uq_graph_relationships_user_id_id"),
        sa.UniqueConstraint(
            "user_id",
            "source_entity_id",
            "normalized_relation_type",
            "target_entity_id",
            name="uq_graph_canonical_relationship",
        ),
    )
    op.create_index(
        op.f("ix_graph_relationships_normalized_relation_type"),
        "graph_relationships",
        ["normalized_relation_type"],
        unique=False,
    )

    # 5. Create document_elements table
    op.create_table(
        "document_elements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("element_index", sa.Integer(), nullable=False),
        sa.Column("element_type", sa.String(length=50), nullable=False),
        sa.Column("parent_element_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR().with_variant(sa.Text(), "sqlite"),
            server_default=sa.FetchedValue(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "document_version",
            "element_index",
            name="uq_document_elements_doc_ver_idx",
        ),
        sa.UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            "id",
            name="uq_document_elements_composite_id",
        ),
    )
    op.create_index(
        "ix_document_elements_search_vector",
        "document_elements",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 6. Create document_processing_runs table
    op.create_table(
        "document_processing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("processing_config_version_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("validation_gate_passed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["processing_config_version_id"], ["processing_config_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            name="uq_processing_runs_user_doc_ver",
        ),
    )
    op.create_index(
        "uq_processing_runs_doc_active",
        "document_processing_runs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("state = 'ACTIVE'"),
    )

    # 7. Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "document_id",
            "document_version",
            "event_type",
            name="uq_outbox_event_idempotency",
        ),
    )

    # 8. Create document_processing_jobs table
    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("lease_token", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["document_processing_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id"],
            ["documents.user_id", "documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_processing_jobs_idempotency_key"
        ),
        sa.UniqueConstraint(
            "run_id", "job_type", name="uq_processing_jobs_run_job_type"
        ),
    )
    op.create_index(
        op.f("ix_document_processing_jobs_idempotency_key"),
        "document_processing_jobs",
        ["idempotency_key"],
        unique=False,
    )

    # 9. Create graph_entity_mentions table
    op.create_table(
        "graph_entity_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source_span", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id", "document_version", "element_id"],
            [
                "document_elements.user_id",
                "document_elements.document_id",
                "document_elements.document_version",
                "document_elements.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "entity_id"],
            ["graph_entities.user_id", "graph_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id",
            "document_id",
            "document_version",
            "element_id",
            name="uq_entity_mention_provenance",
        ),
    )

    # 10. Create graph_relationship_evidence table
    op.create_table(
        "graph_relationship_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("source_element_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source_span", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "document_id", "document_version", "source_element_id"],
            [
                "document_elements.user_id",
                "document_elements.document_id",
                "document_elements.document_version",
                "document_elements.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "relationship_id"],
            ["graph_relationships.user_id", "graph_relationships.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "relationship_id",
            "document_id",
            "document_version",
            "source_element_id",
            name="uq_relationship_evidence_provenance",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("graph_relationship_evidence")
    op.drop_table("graph_entity_mentions")
    op.drop_index(
        op.f("ix_document_processing_jobs_idempotency_key"),
        table_name="document_processing_jobs",
    )
    op.drop_table("document_processing_jobs")
    op.drop_table("outbox_events")
    op.drop_index(
        "uq_processing_runs_doc_active",
        table_name="document_processing_runs",
        postgresql_where=sa.text("state = 'ACTIVE'"),
    )
    op.drop_table("document_processing_runs")
    op.drop_index(
        "ix_document_elements_search_vector",
        table_name="document_elements",
        postgresql_using="gin",
    )
    op.drop_table("document_elements")
    op.drop_index(
        op.f("ix_graph_relationships_normalized_relation_type"),
        table_name="graph_relationships",
    )
    op.drop_table("graph_relationships")
    op.drop_index(
        op.f("ix_graph_entities_normalized_type"), table_name="graph_entities"
    )
    op.drop_index(
        op.f("ix_graph_entities_normalized_name"), table_name="graph_entities"
    )
    op.drop_table("graph_entities")

    op.drop_constraint(
        "fk_documents_processing_config_version", "documents", type_="foreignkey"
    )
    op.drop_constraint("ck_documents_version_ge_active", "documents", type_="check")
    op.drop_constraint("ck_documents_active_version_nonneg", "documents", type_="check")
    op.drop_constraint("uq_documents_user_checksum", "documents", type_="unique")
    op.drop_constraint("uq_documents_user_id_id", "documents", type_="unique")
    op.alter_column(
        "documents",
        "file_size",
        existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        type_=sa.INTEGER(),
        existing_nullable=False,
    )
    op.drop_column("documents", "active_processing_config_version_id")
    op.drop_column("documents", "active_version")
    op.drop_column("documents", "version")

    op.drop_index(
        op.f("ix_processing_config_versions_config_identifier"),
        table_name="processing_config_versions",
    )
    op.drop_table("processing_config_versions")
