from app.auth.domain.interfaces import PasswordHasher
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHash, VerifyMismatchError


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._hasher = Argon2Hasher()

    def hash(self, password: str) -> str:
        """
        Hash a plain text password using Argon2id.
        """
        return self._hasher.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """
        Verify a password against the stored Argon2id hash.
        """
        try:
            return self._hasher.verify(hashed, password)
        except (VerifyMismatchError, InvalidHash):
            return False
