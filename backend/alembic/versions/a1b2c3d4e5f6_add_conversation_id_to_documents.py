"""Add conversation_id to documents table

Revision ID: a1b2c3d4e5f6
Revises: 6d9831113f21
Create Date: 2026-08-08 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "8b635d42caa0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add conversation_id column to documents table
    op.add_column(
        "documents", sa.Column("conversation_id", sa.UUID(as_uuid=True), nullable=True)
    )

    # Create foreign key constraint
    op.create_foreign_key(
        "fk_documents_conversation_id_conversations",
        "documents",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create index for faster lookups
    op.create_index("ix_documents_conversation_id", "documents", ["conversation_id"])


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_documents_conversation_id", table_name="documents")

    # Drop foreign key
    op.drop_constraint(
        "fk_documents_conversation_id_conversations", "documents", type_="foreignkey"
    )

    # Drop column
    op.drop_column("documents", "conversation_id")
