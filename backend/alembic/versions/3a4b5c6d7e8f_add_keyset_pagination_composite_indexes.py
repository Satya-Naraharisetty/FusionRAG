"""add_keyset_pagination_composite_indexes

Revision ID: 3a4b5c6d7e8f
Revises: 2129ce1a6bd9
Create Date: 2026-09-01 02:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a4b5c6d7e8f"
down_revision: str | Sequence[str] | None = "2129ce1a6bd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create keyset pagination indexes."""
    # 1. Partial B-Tree index for active conversation keyset traversal
    op.create_index(
        "ix_conversations_user_last_msg_id",
        "conversations",
        ["user_id", sa.text("last_message_at DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_where=sa.text("state <> 'deleted'"),
    )

    # 2. Composite B-Tree index for message history keyset traversal
    op.create_index(
        "ix_conv_messages_conv_created_id",
        "conversation_messages",
        ["conversation_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop keyset pagination indexes."""
    op.drop_index(
        "ix_conv_messages_conv_created_id", table_name="conversation_messages"
    )
    op.drop_index("ix_conversations_user_last_msg_id", table_name="conversations")
