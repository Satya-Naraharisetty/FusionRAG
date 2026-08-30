from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from app.auth.domain.schemas import (
    EmailVerificationTokenDomain,
    SessionDomain,
    UserDomain,
)


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str:
        """
        Hash a plain password.
        """
        pass

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """
        Verify a password against a hash.
        """
        pass


class TokenProvider(ABC):
    @abstractmethod
    def create_access_token(self, claims: dict[str, Any]) -> str:
        """
        Create a stateless access token.
        """
        pass

    @abstractmethod
    def create_refresh_token(self, claims: dict[str, Any]) -> str:
        """
        Create a refresh token.
        """
        pass

    @abstractmethod
    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and verify a token, returning its claims.
        """
        pass


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> UserDomain | None:
        """
        Fetch a user by email address.
        """
        pass

    @abstractmethod
    async def get_by_id(self, id: UUID) -> UserDomain | None:
        """
        Fetch a user by UUID.
        """
        pass

    @abstractmethod
    async def save(self, user: UserDomain) -> UserDomain:
        """
        Save a user entity.
        """
        pass

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """
        Permanently delete a user. Dependent rows (sessions, conversations,
        documents) are removed by the database ON DELETE CASCADE constraints.
        """
        pass

    @abstractmethod
    async def get_by_oauth_sub(self, provider: str, sub: str) -> "UserDomain | None":
        """
        Fetch a user by OAuth provider + subject identifier.
        """
        pass

    @abstractmethod
    async def delete_unverified_older_than(self, cutoff: datetime) -> int:
        """
        Permanently delete unverified accounts created before the cutoff datetime.
        Returns the count of deleted accounts.
        """
        pass


class SessionRepository(ABC):
    @abstractmethod
    async def find_active_by_token(self, token: str) -> SessionDomain | None:
        """
        Find an active session by raw refresh token.
        """
        pass

    @abstractmethod
    async def find_by_token(self, token: str) -> SessionDomain | None:
        """
        Find any session (active, expired, or revoked) by raw refresh token.
        """
        pass

    @abstractmethod
    async def create(self, session: SessionDomain, raw_token: str) -> SessionDomain:
        """
        Create a new session record.
        """
        pass

    @abstractmethod
    async def revoke(self, token: str) -> None:
        """
        Revoke a session by raw refresh token.
        """
        pass

    @abstractmethod
    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """
        Revoke all active sessions for a user.
        """
        pass

    @abstractmethod
    async def update_last_used(self, token: str, last_used_at: datetime) -> None:
        """
        Update the last_used_at timestamp of a session.
        """
        pass


class EmailVerificationRepository(ABC):
    @abstractmethod
    async def create(
        self, verification_token: EmailVerificationTokenDomain
    ) -> EmailVerificationTokenDomain:
        """
        Save a new email verification token.
        """
        pass

    @abstractmethod
    async def get_by_token_hash(
        self, token_hash: str
    ) -> EmailVerificationTokenDomain | None:
        """
        Find an email verification record by hashed URL token.
        """
        pass

    @abstractmethod
    async def get_latest_by_user_id(
        self, user_id: UUID
    ) -> EmailVerificationTokenDomain | None:
        """
        Find the most recent pending email verification record for a user.
        """
        pass

    @abstractmethod
    async def increment_attempts(self, token_id: UUID) -> int:
        """
        Increment the failed attempt counter for a token and return the new count.
        """
        pass

    @abstractmethod
    async def mark_used(self, token_id: UUID) -> None:
        """
        Mark a verification token as used.
        """
        pass

    @abstractmethod
    async def invalidate_all_for_user(self, user_id: UUID) -> None:
        """
        Invalidate (mark used/expired) any pending verification tokens for a user.
        """
        pass


class TimeProvider(ABC):
    @abstractmethod
    def get_now(self) -> datetime:
        """
        Get the current datetime (timezone-aware UTC).
        """
        pass


class UUIDGenerator(ABC):
    @abstractmethod
    def generate(self) -> UUID:
        """
        Generate a random UUID.
        """
        pass


class UnitOfWork(ABC):
    @abstractmethod
    async def commit(self) -> None:
        """
        Commit the active database transaction context.
        """
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """
        Rollback the active database transaction context.
        """
        pass
