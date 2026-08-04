from abc import ABC, abstractmethod

from app.core.config import settings


class BaseFeatureFlagProvider(ABC):
    @abstractmethod
    def is_enabled(self, flag_name: str, context: dict | None = None) -> bool:
        """Check if a feature flag is enabled."""
        pass


class SettingsFeatureFlagProvider(BaseFeatureFlagProvider):
    def is_enabled(self, flag_name: str, context: dict | None = None) -> bool:
        # Convert flags like "semantic_cache" or "ENABLE_SEMANTIC_CACHE" to settings matching fields
        name = flag_name.upper()
        if not name.startswith("ENABLE_"):
            name = f"ENABLE_{name}"

        # Default fallbacks
        try:
            return getattr(settings, name, False)
        except Exception:
            return False


class FeatureFlagService:
    def __init__(self, provider: BaseFeatureFlagProvider) -> None:
        self._provider = provider

    def is_enabled(self, flag_name: str, context: dict | None = None) -> bool:
        return self._provider.is_enabled(flag_name, context)
