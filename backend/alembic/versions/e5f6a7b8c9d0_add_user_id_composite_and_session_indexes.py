"""add_user_id_composite_and_session_indexes

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08-29 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create composite indexes on documents and foreign key index on refresh_sessions."""
    op.create_index(
        op.f("ix_documents_user_id_scope"),
        "documents",
        ["user_id", "scope"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_user_id_conversation_id"),
        "documents",
        ["user_id", "conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"),
        "refresh_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop composite indexes on documents and foreign key index on refresh_sessions."""
    op.drop_index(op.f("ix_refresh_sessions_user_id"), table_name="refresh_sessions")
    op.drop_index(op.f("ix_documents_user_id_conversation_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_user_id_scope"), table_name="documents")
