from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class DeleteAccountSchema(BaseModel):
    """
    Body for DELETE /auth/account.

    Requires the account password to be re-entered so that a stolen access
    token alone cannot destroy the account (account-takeover protection).
    """

    password: str


class UserResponseSchema(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserDomain(BaseModel):
    id: UUID
    email: EmailStr
    hashed_password: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
