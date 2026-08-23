import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.auth.infrastructure.persistence.models import SQLAlchemyUserEncryptionKey
from app.core.security.crypto import (
    EnvelopeEncryptionService,
    crypto_service,
)


class UserKeyManager:
    """
    Manages persistence and retrieval of per-user Data Encryption Keys (DEKs).
    Coordinates between the DB persistence layer and the in-memory envelope crypto service.
    """

    def __init__(self, service: EnvelopeEncryptionService | None = None):
        self.crypto = service or crypto_service

    def get_or_create_dek_sync(self, db: Session, user_id: uuid.UUID) -> bytes:
        """
        Synchronously retrieves the user's DEK from cache/DB or provisions a new one.
        """
        cached = self.crypto.get_cached_dek(user_id)
        if cached:
            return cached

        record = db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        ).scalar_one_or_none()

        if record is not None:
            dek = self.crypto.unwrap_dek(record.wrapped_dek, user_id)
            self.crypto.cache_dek(user_id, dek)
            return dek

        # Provision new DEK
        new_dek = self.crypto.generate_user_dek()
        wrapped = self.crypto.wrap_dek(new_dek, user_id)
        new_record = SQLAlchemyUserEncryptionKey(
            user_id=user_id,
            wrapped_dek=wrapped,
            key_version=1,
        )
        db.add(new_record)
        db.flush()
        self.crypto.cache_dek(user_id, new_dek)
        return new_dek

    async def get_or_create_dek_async(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> bytes:
        """
        Asynchronously retrieves the user's DEK from cache/DB or provisions a new one.
        """
        cached = self.crypto.get_cached_dek(user_id)
        if cached:
            return cached

        result = await db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        )
        record = result.scalar_one_or_none()

        if record is not None:
            dek = self.crypto.unwrap_dek(record.wrapped_dek, user_id)
            self.crypto.cache_dek(user_id, dek)
            return dek

        # Provision new DEK
        new_dek = self.crypto.generate_user_dek()
        wrapped = self.crypto.wrap_dek(new_dek, user_id)
        new_record = SQLAlchemyUserEncryptionKey(
            user_id=user_id,
            wrapped_dek=wrapped,
            key_version=1,
        )
        db.add(new_record)
        await db.flush()
        self.crypto.cache_dek(user_id, new_dek)
        return new_dek

    def shred_user_dek_sync(self, db: Session, user_id: uuid.UUID) -> bool:
        """
        Crypto-shreds a user's encryption key synchronously:
        1. Purges DEK from memory cache.
        2. Deletes the DEK row from the database.
        """
        self.crypto.purge_cached_dek(user_id)
        record = db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        ).scalar_one_or_none()
        if record:
            db.delete(record)
            db.flush()
            return True
        return False

    async def shred_user_dek_async(self, db: AsyncSession, user_id: uuid.UUID) -> bool:
        """
        Crypto-shreds a user's encryption key asynchronously.
        """
        self.crypto.purge_cached_dek(user_id)
        result = await db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        )
        record = result.scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.flush()
            return True
        return False


user_key_manager = UserKeyManager()
