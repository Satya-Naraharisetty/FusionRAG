import uuid

import pytest

from app.core.security.crypto import (
    CryptoError,
    EnvelopeEncryptionService,
)


def test_master_key_initialization():
    """Verify master key initialization supports string and custom keys."""
    service = EnvelopeEncryptionService(master_key="test-master-key-32-chars-long-123")
    assert len(service._master_key_bytes) == 32


def test_dek_generation_and_wrapping():
    """Verify generating DEK and wrapping/unwrapping with AAD bound to user_id."""
    service = EnvelopeEncryptionService()
    user_id = uuid.uuid4()

    dek = service.generate_user_dek()
    assert len(dek) == 32  # 256 bits

    wrapped = service.wrap_dek(dek, user_id)
    assert isinstance(wrapped, str)

    unwrapped = service.unwrap_dek(wrapped, user_id)
    assert unwrapped == dek

    # Unwrapping with a different user_id must fail (AAD mismatch)
    other_user = uuid.uuid4()
    with pytest.raises(CryptoError):
        service.unwrap_dek(wrapped, other_user)


def test_text_encryption_and_decryption():
    """Verify AES-256-GCM text encryption and decryption."""
    service = EnvelopeEncryptionService()
    user_id = uuid.uuid4()
    dek = service.generate_user_dek()

    secret_message = "Confidential GDPR user document and private conversation."
    encrypted = service.encrypt_text(secret_message, dek, aad=user_id.bytes)

    assert encrypted != secret_message
    assert isinstance(encrypted, str)

    decrypted = service.decrypt_text(encrypted, dek, aad=user_id.bytes)
    assert decrypted == secret_message


def test_tamper_detection_aes_gcm():
    """Verify that tampering with ciphertext fails authentication tag check."""
    service = EnvelopeEncryptionService()
    dek = service.generate_user_dek()

    original = b"Sensitive binary payload"
    encrypted = service.encrypt_bytes(original, dek)

    # Tamper with 1 byte in the ciphertext payload
    tampered = bytearray(encrypted)
    tampered[-1] ^= 0xFF
    tampered_bytes = bytes(tampered)

    with pytest.raises(CryptoError):
        service.decrypt_bytes(tampered_bytes, dek)


def test_dek_caching_and_purge():
    """Verify DEK in-memory caching and cache purging."""
    service = EnvelopeEncryptionService()
    user_id = uuid.uuid4()
    dek = service.generate_user_dek()

    assert service.get_cached_dek(user_id) is None

    service.cache_dek(user_id, dek)
    assert service.get_cached_dek(user_id) == dek

    service.purge_cached_dek(user_id)
    assert service.get_cached_dek(user_id) is None


def test_crypto_shredding_simulation():
    """
    Simulates crypto-shredding:
    Even if backups contain the encrypted payload, destroying the user's DEK
    makes decryption mathematically impossible.
    """
    service = EnvelopeEncryptionService()
    user_id = uuid.uuid4()
    user_dek = service.generate_user_dek()

    payload = "Important user tax return details and sensitive chat."
    backup_stored_ciphertext = service.encrypt_text(
        payload, user_dek, aad=user_id.bytes
    )

    # User requests deletion -> Destroy/Shred user_dek
    del user_dek
    random_other_dek = service.generate_user_dek()

    # Attempting to decrypt backup ciphertext with any other key fails
    with pytest.raises(CryptoError):
        service.decrypt_text(
            backup_stored_ciphertext, random_other_dek, aad=user_id.bytes
        )
