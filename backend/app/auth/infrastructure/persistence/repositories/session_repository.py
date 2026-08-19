import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.interfaces import SessionRepository
from app.auth.domain.schemas import SessionDomain
from app.auth.infrastructure.persistence.models import SQLAlchemySession


class SQLAlchemySessionRepository(SessionRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _hash_token(self, token: str) -> str:
        """
        Cryptographically hashes the raw token string (SHA-256).
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def find_active_by_token(self, token: str) -> SessionDomain | None:
        """
        Query an active, unrevoked session by raw token string.
        Applies row locking (with_for_update) to prevent concurrency race issues.
        """
        token_hash = self._hash_token(token)
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(SQLAlchemySession)
            .where(
                SQLAlchemySession.token_hash == token_hash,
                SQLAlchemySession.is_revoked == False,
                SQLAlchemySession.expires_at > now,
            )
            .with_for_update()
        )
        db_session = result.scalar_one_or_none()
        if not db_session:
            return None
        return SessionDomain.model_validate(db_session)

    async def find_by_token(self, token: str) -> SessionDomain | None:
        """
        Query any session (including revoked or expired) by raw token string.
        """
        token_hash = self._hash_token(token)
        result = await self._db.execute(
            select(SQLAlchemySession).where(SQLAlchemySession.token_hash == token_hash)
        )
        db_session = result.scalar_one_or_none()
        if not db_session:
            return None
        return SessionDomain.model_validate(db_session)

    async def create(self, session: SessionDomain, raw_token: str) -> SessionDomain:
        """
        Save a new session, hashing the token internally and flushing the database session.
        """
        token_hash = self._hash_token(raw_token)
        db_session = SQLAlchemySession(
            id=session.id,
            token_hash=token_hash,
            user_id=session.user_id,
            expires_at=session.expires_at,
            is_revoked=session.is_revoked,
            created_at=session.created_at,
            last_used_at=session.last_used_at,
            revoked_at=session.revoked_at,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
        )
        self._db.add(db_session)
        await self._db.flush()
        await self._db.refresh(db_session)
        return SessionDomain.model_validate(db_session)

    async def revoke(self, token: str) -> None:
        """
        Revoke a session by raw token.
        """
        token_hash = self._hash_token(token)
        result = await self._db.execute(
            select(SQLAlchemySession).where(SQLAlchemySession.token_hash == token_hash)
        )
        db_session = result.scalar_one_or_none()
        if db_session:
            db_session.is_revoked = True
            db_session.revoked_at = datetime.now(UTC)
            await self._db.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """
        Revoke all active sessions associated with a user ID.
        """
        result = await self._db.execute(
            select(SQLAlchemySession).where(
                SQLAlchemySession.user_id == user_id,
                SQLAlchemySession.is_revoked == False,
            )
        )
        db_sessions = result.scalars().all()
        now = datetime.now(UTC)
        for s in db_sessions:
            s.is_revoked = True
            s.revoked_at = now
        await self._db.flush()

    async def update_last_used(self, token: str, last_used_at: datetime) -> None:
        """
        Update the last_used_at timestamp of an active session.
        """
        token_hash = self._hash_token(token)
        result = await self._db.execute(
            select(SQLAlchemySession).where(SQLAlchemySession.token_hash == token_hash)
        )
        db_session = result.scalar_one_or_none()
        if db_session:
            db_session.last_used_at = last_used_at
            await self._db.flush()
