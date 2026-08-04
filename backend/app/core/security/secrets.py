import os
from abc import ABC, abstractmethod


class BaseSecretManager(ABC):
    @abstractmethod
    def get_secret(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a secret string by its key name."""
        pass


class EnvSecretManager(BaseSecretManager):
    def get_secret(self, key: str, default: str | None = None) -> str | None:
        # Fallback to standard environment variables
        return os.getenv(key, default)
