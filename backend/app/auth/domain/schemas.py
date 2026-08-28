from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
)

# Banned common weak passwords as per modern NIST recommendations
BANNED_PASSWORDS = {
    "12345678",
    "password",
    "password123",
    "admin123",
    "qwertyuiop",
    "welcome1",
    "welcome123",
}


class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, v: str) -> str:
        """
        Enforce backend password strength rules.
        """
        if v.lower() in BANNED_PASSWORDS:
            raise ValueError("Password is too common and easily guessed.")
        return v


class UserLoginSchema(BaseModel):
    email: EmailStr
    password: str


class UpdatePasswordSchema(BaseModel):
    current_password: str | None = None
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_policy(cls, v: str) -> str:
        """
        Enforce backend password strength rules.
        """
        if v.lower() in BANNED_PASSWORDS:
            raise ValueError("Password is too common and easily guessed.")
        return v


class DeleteAccountSchema(BaseModel):
    """
    Body for DELETE /auth/account.

    Requires the account password to be re-entered if the user has one,
    so that a stolen access token alone cannot destroy the account (account-takeover protection).
    """

    password: str | None = None


class UserResponseSchema(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    is_active: bool
    is_verified: bool = False
    created_at: datetime
    updated_at: datetime
    oauth_provider: str | None = None
    has_password: bool = False

    model_config = ConfigDict(from_attributes=True)


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MagicLinkRequestSchema(BaseModel):
    email: EmailStr


class VerifyEmailSchema(BaseModel):
    token: str | None = None
    email: EmailStr | None = None
    otp: str | None = None


class ResendVerificationSchema(BaseModel):
    email: EmailStr


class UserDomain(BaseModel):
    id: UUID
    email: EmailStr
    # None for OAuth-only accounts that have no password
    hashed_password: str | None = None
    role: str
    is_active: bool
    is_verified: bool = False
    created_at: datetime
    updated_at: datetime
    oauth_provider: str | None = None
    oauth_sub: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    def has_password(self) -> bool:
        return bool(self.hashed_password)


class SessionDomain(BaseModel):
    id: UUID
    token_hash: str
    user_id: UUID
    expires_at: datetime
    is_revoked: bool
    created_at: datetime
    last_used_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None
    ip_address: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EmailVerificationTokenDomain(BaseModel):
    id: UUID
    user_id: UUID
    token_hash: str
    otp_code: str
    attempts: int = 0
    expires_at: datetime
    is_used: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSettingsResponseSchema(BaseModel):
    user_id: UUID
    folders: list[dict[str, Any]] = Field(default_factory=list)
    pinned_conversations: list[str] = Field(default_factory=list)
    conversation_tags: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    document_folders: list[dict[str, Any]] = Field(default_factory=list)
    document_folder_mappings: dict[str, str] = Field(default_factory=dict)
    document_custom_order: list[str] = Field(default_factory=list)
    document_filter_presets: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSettingsPatchSchema(BaseModel):
    folders: list[dict[str, Any]] | None = None
    pinned_conversations: list[str] | None = None
    conversation_tags: dict[str, list[dict[str, Any]]] | None = None
    document_folders: list[dict[str, Any]] | None = None
    document_folder_mappings: dict[str, str] | None = None
    document_custom_order: list[str] | None = None
    document_filter_presets: list[dict[str, Any]] | None = None
    preferences: dict[str, Any] | None = None
