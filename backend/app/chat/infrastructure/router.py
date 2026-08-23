import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.chat.domain.agents import ToolDefinition
from app.chat.domain.interfaces import (
    ChatMessage,
    LLMProvider,
    ProviderResponse,
    StreamChunk,
)
from app.core.reliability.circuit_breaker import (
    CircuitBreaker,
)

logger = logging.getLogger(__name__)


class RoutingPolicy(ABC):
    @abstractmethod
    def select_provider_key(
        self,
        model_name: str,
        providers: dict[str, LLMProvider],
        breakers: dict[str, CircuitBreaker],
    ) -> str:
        """Select the target provider key for the given model name."""
        pass


class SettingsRoutingPolicy(RoutingPolicy):
    def __init__(
        self,
        primary_provider_key: str = "gemini",
        backup_provider_key: str | None = None,
    ) -> None:
        self.primary = primary_provider_key
        self.backup = backup_provider_key

    def select_provider_key(
        self,
        model_name: str,
        providers: dict[str, LLMProvider],
        breakers: dict[str, CircuitBreaker],
    ) -> str:
        target = self.primary
        if target in providers:
            breaker = breakers.get(target)
            if (
                breaker
                and breaker.state == "OPEN"
                and self.backup
                and self.backup in providers
            ):
                logger.warning(
                    f"Primary provider '{target}' circuit is OPEN. Failing over to '{self.backup}'."
                )
                return self.backup
            return target
        return next(iter(providers.keys())) if providers else self.primary


class LLMProviderRouter(LLMProvider):
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        policy: RoutingPolicy,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._providers = providers
        self._policy = policy
        self._breakers = {
            k: CircuitBreaker(
                failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
            )
            for k in providers.keys()
        }

    def get_circuit_breaker(self, provider_key: str) -> CircuitBreaker | None:
        return self._breakers.get(provider_key)

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> ProviderResponse:
        provider_key = self._policy.select_provider_key(
            model, self._providers, self._breakers
        )
        provider = self._providers[provider_key]
        breaker = self._breakers[provider_key]

        # Use fallback model name for backup if we failed over
        actual_model = model
        if provider_key == "openai" and "gemini" in model:
            actual_model = "gpt-4o-mini"  # Default backup model
        elif provider_key == "gemini" and "gpt" in model:
            actual_model = "gemini-3.5-flash-lite"  # Default backup model

        logger.info(
            f"Routing generate request to provider: {provider_key} (Model: {actual_model})"
        )

        try:
            return await breaker.call(
                provider.generate,
                messages=messages,
                model=actual_model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
            )
        except Exception as e:
            logger.error(f"Generation failed on provider {provider_key}: {e}")
            # If failover is possible, try the other provider once
            fallback_key = (
                getattr(self._policy, "backup", None)
                if provider_key == getattr(self._policy, "primary", None)
                else getattr(self._policy, "primary", None)
            )
            if fallback_key and fallback_key in self._providers:
                fallback_provider = self._providers[fallback_key]
                fallback_model = actual_model
                logger.warning(f"Attempting immediate fallback to: {fallback_key}")
                try:
                    return await fallback_provider.generate(
                        messages=messages,
                        model=fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=tools,
                        tool_choice=tool_choice,
                    )
                except Exception as ex:
                    logger.critical(
                        f"Fallback provider {fallback_key} also failed: {ex}"
                    )
                    raise ex
            raise e

    async def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        provider_key = self._policy.select_provider_key(
            model, self._providers, self._breakers
        )
        provider = self._providers[provider_key]
        breaker = self._breakers[provider_key]

        actual_model = model
        if provider_key == "openai" and "gemini" in model:
            actual_model = "gpt-4o-mini"
        elif provider_key == "gemini" and "gpt" in model:
            actual_model = "gemini-3.5-flash-lite"

        logger.info(
            f"Routing stream request to provider: {provider_key} (Model: {actual_model})"
        )

        # Verify circuit status before stream starts
        await breaker.check_state()

        try:
            # Consume stream and record success/failure
            async for chunk in provider.stream(
                messages=messages,
                model=actual_model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
            ):
                yield chunk
            await breaker.record_success()
        except Exception as e:
            await breaker.record_failure()
            logger.error(f"Streaming failed on provider {provider_key}: {e}")
            raise e
