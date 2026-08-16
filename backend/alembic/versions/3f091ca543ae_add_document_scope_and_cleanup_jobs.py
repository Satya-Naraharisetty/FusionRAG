"""add_document_scope_and_cleanup_jobs

Revision ID: 3f091ca543ae
Revises: a1b2c3d4e5f6
Create Date: 2026-08-16 16:57:10.636824

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f091ca543ae"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create durable_cleanup_jobs table
    op.create_table(
        "durable_cleanup_jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create uniqueness index/constraint on (resource_type, resource_id) to prevent duplicate jobs
    op.create_index(
        "uq_cleanup_resource",
        "durable_cleanup_jobs",
        ["resource_type", "resource_id"],
        unique=True,
    )

    # 2. Add nullable scope column to documents table
    op.add_column("documents", sa.Column("scope", sa.String(50), nullable=True))

    # Update existing rows to default to 'CONVERSATION' if conversation_id is present, else 'LIBRARY'
    op.execute(
        "UPDATE documents SET scope = 'CONVERSATION' WHERE conversation_id IS NOT NULL"
    )
    op.execute("UPDATE documents SET scope = 'LIBRARY' WHERE conversation_id IS NULL")

    # Alter column to be not null
    op.alter_column(
        "documents",
        "scope",
        existing_type=sa.String(50),
        nullable=False,
        server_default="LIBRARY",
    )

    # Create CheckConstraint on scope and conversation_id
    op.create_check_constraint(
        "chk_document_scope_conversation",
        "documents",
        "(scope = 'LIBRARY' AND conversation_id IS NULL) OR (scope = 'CONVERSATION' AND conversation_id IS NOT NULL)",
    )

    # Create indexes on documents table
    op.create_index("ix_documents_user_id_scope", "documents", ["user_id", "scope"])
    op.create_index(
        "ix_documents_user_id_conversation_id",
        "documents",
        ["user_id", "conversation_id"],
    )
    op.create_index(
        "ix_documents_conversation_id_scope", "documents", ["conversation_id", "scope"]
    )


def downgrade() -> None:
    # Drop indexes on documents table
    op.drop_index("ix_documents_conversation_id_scope", table_name="documents")
    op.drop_index("ix_documents_user_id_conversation_id", table_name="documents")
    op.drop_index("ix_documents_user_id_scope", table_name="documents")

    # Drop check constraint
    op.drop_constraint("chk_document_scope_conversation", "documents", type_="check")

    # Drop scope column
    op.drop_column("documents", "scope")

    # Drop durable_cleanup_jobs index & table
    op.drop_index("uq_cleanup_resource", table_name="durable_cleanup_jobs")
    op.drop_table("durable_cleanup_jobs")
