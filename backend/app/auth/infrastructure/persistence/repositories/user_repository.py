from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.interfaces import UserRepository
from app.auth.domain.schemas import UserDomain
from app.auth.infrastructure.persistence.models import SQLAlchemyUser


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> UserDomain | None:
        """
        Query a user by normalized email address.
        """
        result = await self._db.execute(
            select(SQLAlchemyUser).where(SQLAlchemyUser.email == email)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            return None
        return UserDomain.model_validate(db_user)

    async def get_by_id(self, id: UUID) -> UserDomain | None:
        """
        Query a user by UUID.
        """
        result = await self._db.execute(
            select(SQLAlchemyUser).where(SQLAlchemyUser.id == id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            return None
        return UserDomain.model_validate(db_user)

    async def get_by_oauth_sub(self, provider: str, sub: str) -> UserDomain | None:
        """
        Query a user by OAuth provider + subject identifier.
        """
        result = await self._db.execute(
            select(SQLAlchemyUser).where(
                SQLAlchemyUser.oauth_provider == provider,
                SQLAlchemyUser.oauth_sub == sub,
            )
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            return None
        return UserDomain.model_validate(db_user)

    async def save(self, user: UserDomain) -> UserDomain:
        """
        Save/persist a user model in the database transaction context.
        """
        result = await self._db.execute(
            select(SQLAlchemyUser).where(SQLAlchemyUser.id == user.id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = SQLAlchemyUser(
                id=user.id,
                email=user.email,
                hashed_password=user.hashed_password,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
                oauth_provider=user.oauth_provider,
                oauth_sub=user.oauth_sub,
            )
            self._db.add(db_user)
        else:
            db_user.email = user.email
            db_user.hashed_password = user.hashed_password
            db_user.role = user.role
            db_user.is_active = user.is_active
            db_user.updated_at = user.updated_at
            # Update OAuth fields if provided
            if user.oauth_provider is not None:
                db_user.oauth_provider = user.oauth_provider
            if user.oauth_sub is not None:
                db_user.oauth_sub = user.oauth_sub

        await self._db.flush()
        await self._db.refresh(db_user)
        return UserDomain.model_validate(db_user)

    async def delete(self, user_id: UUID) -> None:
        """
        Permanently delete a user by UUID.

        The database ON DELETE CASCADE constraints remove the user's sessions,
        conversations, and documents.
        """
        await self._db.execute(
            delete(SQLAlchemyUser).where(SQLAlchemyUser.id == user_id)
        )
        await self._db.flush()
