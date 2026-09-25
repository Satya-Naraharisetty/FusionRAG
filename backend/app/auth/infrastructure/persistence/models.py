import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SQLAlchemyUser(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Ensure each (provider, sub) pair maps to exactly one account
        UniqueConstraint(
            "oauth_provider", "oauth_sub", name="uq_users_oauth_provider_sub"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    # Nullable for OAuth-only users who have no local password
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # OAuth fields — None for email/password accounts
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_sub: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Relationships
    sessions: Mapped[list["SQLAlchemySession"]] = relationship(
        "SQLAlchemySession", back_populates="user", cascade="all, delete-orphan"
    )
    encryption_key: Mapped[Optional["SQLAlchemyUserEncryptionKey"]] = relationship(
        "SQLAlchemyUserEncryptionKey",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    verification_tokens: Mapped[list["SQLAlchemyEmailVerificationToken"]] = (
        relationship(
            "SQLAlchemyEmailVerificationToken",
            back_populates="user",
            cascade="all, delete-orphan",
        )
    )
    settings: Mapped[Optional["SQLAlchemyUserSettings"]] = relationship(
        "SQLAlchemyUserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SQLAlchemySession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_sessions_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    user: Mapped["SQLAlchemyUser"] = relationship(
        "SQLAlchemyUser", back_populates="sessions"
    )


class SQLAlchemyUserEncryptionKey(Base):
    __tablename__ = "user_encryption_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(default=1, nullable=False)
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
    user: Mapped["SQLAlchemyUser"] = relationship(
        "SQLAlchemyUser", back_populates="encryption_key"
    )


class SQLAlchemyEmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    otp_code: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["SQLAlchemyUser"] = relationship(
        "SQLAlchemyUser", back_populates="verification_tokens"
    )


class SQLAlchemyUserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    folders: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pinned_conversations: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    conversation_tags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    document_folders: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    document_folder_mappings: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    document_custom_order: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    document_filter_presets: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
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
    user: Mapped["SQLAlchemyUser"] = relationship(
        "SQLAlchemyUser", back_populates="settings"
    )
