import os
from abc import ABC, abstractmethod
from typing import Optional


class BaseSecretManager(ABC):
    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a secret string by its key name."""
        pass


class EnvSecretManager(BaseSecretManager):
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # Fallback to standard environment variables
        return os.getenv(key, default)
