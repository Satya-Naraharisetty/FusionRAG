"""add_user_settings_table

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-28 22:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("folders", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "pinned_conversations", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("conversation_tags", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("document_folders", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "document_folder_mappings",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "document_custom_order", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "document_filter_presets", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
