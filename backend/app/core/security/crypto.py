import base64
import hashlib
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class CryptoError(Exception):
    """Raised when cryptographic encryption or decryption fails."""

    pass


class KeyNotFoundError(CryptoError):
    """Raised when a user's Data Encryption Key (DEK) has been shredded or does not exist."""

    pass


class EnvelopeEncryptionService:
    """
    Provides Envelope Encryption and per-user Data Encryption Keys (DEK) for Crypto-Shredding.

    - Master Key (KEK): 256-bit Key Encryption Key used to wrap/unwrap user DEKs.
    - User DEK: 256-bit AES key unique to each user for encrypting their documents,
      chunks, and chat history using AES-256-GCM.
    - Crypto-Shredding: Dropping a user's DEK renders all their encrypted data
      in backups, disk, and object storage mathematically unrecoverable.
    """

    NONCE_SIZE = 12  # 96-bit nonce standard for AES-GCM

    def __init__(self, master_key: str | None = None):
        raw_key = master_key or getattr(
            settings,
            "ENCRYPTION_MASTER_KEY",
            "default-insecure-master-key-32-chars-long!!",
        )
        # Ensure 32-byte 256-bit master key
        if isinstance(raw_key, str):
            raw_bytes = raw_key.encode("utf-8")
        else:
            raw_bytes = bytes(raw_key)

        if len(raw_bytes) == 32:
            self._master_key_bytes = raw_bytes
        else:
            self._master_key_bytes = hashlib.sha256(raw_bytes).digest()

        self._master_aesgcm = AESGCM(self._master_key_bytes)
        # In-memory cache for active unwrapped user DEKs: Dict[user_id, bytes]
        self._dek_cache: dict[uuid.UUID, bytes] = {}

    def generate_user_dek(self) -> bytes:
        """Generate a cryptographically secure 256-bit DEK."""
        return AESGCM.generate_key(bit_length=256)

    def wrap_dek(self, dek: bytes, user_id: uuid.UUID) -> str:
        """
        Encrypt the user's DEK with the Master Key (KEK), binding it to the user's UUID.
        Returns a URL-safe Base64 encoded string.
        """
        nonce = os.urandom(self.NONCE_SIZE)
        aad = user_id.bytes
        ciphertext = self._master_aesgcm.encrypt(nonce, dek, aad)
        wrapped_payload = nonce + ciphertext
        return base64.b64encode(wrapped_payload).decode("utf-8")

    def unwrap_dek(self, wrapped_dek_b64: str, user_id: uuid.UUID) -> bytes:
        """
        Decrypt the wrapped DEK using the Master Key.
        """
        try:
            wrapped_payload = base64.b64decode(wrapped_dek_b64.encode("utf-8"))
            if len(wrapped_payload) < self.NONCE_SIZE + 16:
                raise CryptoError("Invalid wrapped DEK length.")
            nonce = wrapped_payload[: self.NONCE_SIZE]
            ciphertext = wrapped_payload[self.NONCE_SIZE :]
            aad = user_id.bytes
            return self._master_aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise CryptoError(f"Failed to unwrap DEK: {e}") from e

    def cache_dek(self, user_id: uuid.UUID, dek: bytes) -> None:
        """Cache decrypted DEK in memory for high-performance requests."""
        self._dek_cache[user_id] = dek

    def get_cached_dek(self, user_id: uuid.UUID) -> bytes | None:
        """Retrieve cached DEK if present."""
        return self._dek_cache.get(user_id)

    def purge_cached_dek(self, user_id: uuid.UUID) -> None:
        """Purge DEK from memory cache (called on logout, eviction, or deletion)."""
        self._dek_cache.pop(user_id, None)

    def encrypt_bytes(self, data: bytes, dek: bytes, aad: bytes | None = None) -> bytes:
        """
        Encrypt raw bytes using the provided DEK with AES-256-GCM.
        Returns: 12-byte Nonce + Ciphertext (with 16-byte GCM auth tag appended).
        """
        try:
            nonce = os.urandom(self.NONCE_SIZE)
            aesgcm = AESGCM(dek)
            ciphertext = aesgcm.encrypt(nonce, data, aad)
            return nonce + ciphertext
        except Exception as e:
            raise CryptoError(f"Encryption failed: {e}") from e

    def decrypt_bytes(
        self, payload: bytes, dek: bytes, aad: bytes | None = None
    ) -> bytes:
        """
        Decrypt payload (Nonce + Ciphertext) using the provided DEK with AES-256-GCM.
        """
        try:
            if len(payload) < self.NONCE_SIZE + 16:
                raise CryptoError("Encrypted payload too short.")
            nonce = payload[: self.NONCE_SIZE]
            ciphertext = payload[self.NONCE_SIZE :]
            aesgcm = AESGCM(dek)
            return aesgcm.decrypt(nonce, ciphertext, aad)
        except Exception as e:
            raise CryptoError(f"Decryption failed: {e}") from e

    def encrypt_text(self, text: str, dek: bytes, aad: bytes | None = None) -> str:
        """Encrypt a UTF-8 text string and return a base64 encoded ciphertext string."""
        encrypted = self.encrypt_bytes(text.encode("utf-8"), dek, aad)
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_text(
        self, b64_payload: str, dek: bytes, aad: bytes | None = None
    ) -> str:
        """Decrypt a base64 encoded ciphertext string into a UTF-8 string."""
        try:
            raw_payload = base64.b64decode(b64_payload.encode("utf-8"))
            decrypted_bytes = self.decrypt_bytes(raw_payload, dek, aad)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            raise CryptoError(f"Text decryption failed: {e}") from e


# Singleton instance
crypto_service = EnvelopeEncryptionService()
