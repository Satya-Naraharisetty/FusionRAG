import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.auth.infrastructure.persistence.models import (
    SQLAlchemyUser,
    SQLAlchemyUserEncryptionKey,
)
from app.core.security.crypto import CryptoError, crypto_service
from app.core.security.key_manager import user_key_manager
from app.db.models import Base
from tests.db import TEST_DATABASE_URL


def test_user_key_manager_lifecycle_and_crypto_shredding():
    """
    End-to-end lifecycle test for UserKeyManager and Crypto-Shredding:
    1. Create user in database.
    2. Retrieve/provision DEK for the user.
    3. Encrypt sensitive user data.
    4. Delete user account and shred DEK.
    5. Verify complete cryptographic erasure across database and cache.
    """
    engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        user_id = uuid.uuid4()
        user = SQLAlchemyUser(
            id=user_id,
            email=f"crypto_{user_id.hex[:8]}@example.com",
            hashed_password="hashed_test_password",
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()

        # 1. Provision DEK for user
        dek = user_key_manager.get_or_create_dek_sync(db, user_id)
        assert len(dek) == 32
        assert crypto_service.get_cached_dek(user_id) == dek

        # 2. Check wrapped DEK row in database
        key_row = db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        ).scalar_one_or_none()
        assert key_row is not None
        assert key_row.wrapped_dek is not None

        # 3. Encrypt sensitive user data
        raw_document = "Sensitive financial report and private medical notes."
        ciphertext = crypto_service.encrypt_text(raw_document, dek, aad=user_id.bytes)
        assert ciphertext != raw_document

        # 4. Decrypt works while key exists
        recovered = crypto_service.decrypt_text(ciphertext, dek, aad=user_id.bytes)
        assert recovered == raw_document

        # 5. Simulate User Account Deletion / GDPR Right to be Forgotten
        # Cascading delete removes user and linked SQLAlchemyUserEncryptionKey
        user_key_manager.shred_user_dek_sync(db, user_id)
        db.delete(user)
        db.commit()

        # 6. Verify DEK is purged from in-memory cache and DB
        assert crypto_service.get_cached_dek(user_id) is None
        deleted_key_row = db.execute(
            select(SQLAlchemyUserEncryptionKey).where(
                SQLAlchemyUserEncryptionKey.user_id == user_id
            )
        ).scalar_one_or_none()
        assert deleted_key_row is None

        # 7. Verify cryptographic erasure (Backups retaining ciphertext cannot be decrypted)
        random_unrelated_dek = crypto_service.generate_user_dek()
        with pytest.raises(CryptoError):
            crypto_service.decrypt_text(
                ciphertext, random_unrelated_dek, aad=user_id.bytes
            )

    finally:
        db.close()
        engine.dispose()
