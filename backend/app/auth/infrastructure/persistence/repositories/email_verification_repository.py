from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.interfaces import EmailVerificationRepository
from app.auth.domain.schemas import EmailVerificationTokenDomain
from app.auth.infrastructure.persistence.models import (
    SQLAlchemyEmailVerificationToken,
)


class SQLAlchemyEmailVerificationRepository(EmailVerificationRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self, verification_token: EmailVerificationTokenDomain
    ) -> EmailVerificationTokenDomain:
        """
        Save a new email verification token.
        """
        db_token = SQLAlchemyEmailVerificationToken(
            id=verification_token.id,
            user_id=verification_token.user_id,
            token_hash=verification_token.token_hash,
            otp_code=verification_token.otp_code,
            attempts=verification_token.attempts,
            expires_at=verification_token.expires_at,
            is_used=verification_token.is_used,
            created_at=verification_token.created_at,
        )
        self._db.add(db_token)
        await self._db.flush()
        await self._db.refresh(db_token)
        return EmailVerificationTokenDomain.model_validate(db_token)

    async def get_by_token_hash(
        self, token_hash: str
    ) -> EmailVerificationTokenDomain | None:
        """
        Find an email verification record by hashed URL token.
        """
        result = await self._db.execute(
            select(SQLAlchemyEmailVerificationToken).where(
                SQLAlchemyEmailVerificationToken.token_hash == token_hash
            )
        )
        db_token = result.scalar_one_or_none()
        if not db_token:
            return None
        return EmailVerificationTokenDomain.model_validate(db_token)

    async def get_latest_by_user_id(
        self, user_id: UUID
    ) -> EmailVerificationTokenDomain | None:
        """
        Find the most recent pending email verification record for a user.
        """
        result = await self._db.execute(
            select(SQLAlchemyEmailVerificationToken)
            .where(
                SQLAlchemyEmailVerificationToken.user_id == user_id,
                SQLAlchemyEmailVerificationToken.is_used == False,  # noqa: E712
            )
            .order_by(desc(SQLAlchemyEmailVerificationToken.created_at))
            .limit(1)
        )
        db_token = result.scalar_one_or_none()
        if not db_token:
            return None
        return EmailVerificationTokenDomain.model_validate(db_token)

    async def increment_attempts(self, token_id: UUID) -> int:
        """
        Increment the failed attempt counter for a token and return the new count.
        """
        result = await self._db.execute(
            select(SQLAlchemyEmailVerificationToken).where(
                SQLAlchemyEmailVerificationToken.id == token_id
            )
        )
        db_token = result.scalar_one_or_none()
        if not db_token:
            return 0
        db_token.attempts += 1
        await self._db.flush()
        await self._db.refresh(db_token)
        return db_token.attempts

    async def mark_used(self, token_id: UUID) -> None:
        """
        Mark a verification token as used.
        """
        await self._db.execute(
            update(SQLAlchemyEmailVerificationToken)
            .where(SQLAlchemyEmailVerificationToken.id == token_id)
            .values(is_used=True)
        )
        await self._db.flush()

    async def invalidate_all_for_user(self, user_id: UUID) -> None:
        """
        Invalidate (mark used) any pending verification tokens for a user.
        """
        await self._db.execute(
            update(SQLAlchemyEmailVerificationToken)
            .where(
                SQLAlchemyEmailVerificationToken.user_id == user_id,
                SQLAlchemyEmailVerificationToken.is_used == False,  # noqa: E712
            )
            .values(is_used=True)
        )
        await self._db.flush()
