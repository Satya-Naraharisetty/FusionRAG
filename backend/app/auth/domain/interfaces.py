from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from app.auth.domain.schemas import SessionDomain, UserDomain


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
    def get_by_email(self, email: str) -> UserDomain | None:
        """
        Fetch a user by email address.
        """
        pass

    @abstractmethod
    def get_by_id(self, id: UUID) -> UserDomain | None:
        """
        Fetch a user by UUID.
        """
        pass

    @abstractmethod
    def save(self, user: UserDomain) -> UserDomain:
        """
        Save a user entity.
        """
        pass

    @abstractmethod
    def delete(self, user_id: UUID) -> None:
        """
        Permanently delete a user. Dependent rows (sessions, conversations,
        documents) are removed by the database ON DELETE CASCADE constraints.
        """
        pass


class SessionRepository(ABC):
    @abstractmethod
    def find_active_by_token(self, token: str) -> SessionDomain | None:
        """
        Find an active session by raw refresh token.
        """
        pass

    @abstractmethod
    def find_by_token(self, token: str) -> SessionDomain | None:
        """
        Find any session (active, expired, or revoked) by raw refresh token.
        """
        pass

    @abstractmethod
    def create(self, session: SessionDomain, raw_token: str) -> SessionDomain:
        """
        Create a new session record.
        """
        pass

    @abstractmethod
    def revoke(self, token: str) -> None:
        """
        Revoke a session by raw refresh token.
        """
        pass

    @abstractmethod
    def revoke_all_for_user(self, user_id: UUID) -> None:
        """
        Revoke all active sessions for a user.
        """
        pass

    @abstractmethod
    def update_last_used(self, token: str, last_used_at: datetime) -> None:
        """
        Update the last_used_at timestamp of a session.
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
    def commit(self) -> None:
        """
        Commit the active database transaction context.
        """
        pass

    @abstractmethod
    def rollback(self) -> None:
        """
        Rollback the active database transaction context.
        """
        pass
