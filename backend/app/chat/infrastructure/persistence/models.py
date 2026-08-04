import uuid
from datetime import datetime

from app.db.session import Base
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ConversationORM(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    settings_json: Mapped[dict] = mapped_column("settings", JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Enable optimistic locking
    __mapper_args__ = {"version_id_col": version}

    messages: Mapped[list["ConversationMessageORM"]] = relationship(
        "ConversationMessageORM",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["ConversationSummaryORM"]] = relationship(
        "ConversationSummaryORM",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ConversationMessageORM(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    structured_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", back_populates="messages"
    )


class ConversationSummaryORM(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    covered_from_message_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    covered_until_message_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation: Mapped["ConversationORM"] = relationship(
        "ConversationORM", back_populates="summaries"
    )
