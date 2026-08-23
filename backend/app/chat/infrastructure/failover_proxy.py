from app.chat.domain.interfaces import LLMProvider
from app.chat.infrastructure.router import LLMProviderRouter, SettingsRoutingPolicy


class ProviderFailoverProxy(LLMProviderRouter):
    """
    A backward-compatible LLMProvider proxy that implements automatic failover policies.
    Binds the primary and backup providers to the new LLMProviderRouter engine.
    """

    def __init__(
        self,
        primary: LLMProvider,
        backup: LLMProvider | None = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        providers = {"gemini": primary}
        if backup is not None:
            providers["backup"] = backup
        policy = SettingsRoutingPolicy(
            primary_provider_key="gemini",
            backup_provider_key="backup" if backup is not None else None,
        )
        super().__init__(
            providers=providers,
            policy=policy,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
