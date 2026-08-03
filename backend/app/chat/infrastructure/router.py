import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional

from app.chat.domain.interfaces import LLMProvider, ChatMessage, ProviderResponse, StreamChunk
from app.chat.domain.agents import ToolDefinition
from app.core.reliability.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger(__name__)


class RoutingPolicy(ABC):
    @abstractmethod
    def select_provider_key(
        self,
        model_name: str,
        providers: Dict[str, LLMProvider],
        breakers: Dict[str, CircuitBreaker],
    ) -> str:
        """Select the target provider key for the given model name."""
        pass


class SettingsRoutingPolicy(RoutingPolicy):
    def __init__(self, primary_provider_key: str, backup_provider_key: str) -> None:
        self.primary = primary_provider_key
        self.backup = backup_provider_key

    def select_provider_key(
        self,
        model_name: str,
        providers: Dict[str, LLMProvider],
        breakers: Dict[str, CircuitBreaker],
    ) -> str:
        # Determine based on model name prefix first
        model_lower = model_name.lower()
        target = self.primary
        if "gpt" in model_lower or "openai" in model_lower:
            target = "openai"
        elif "gemini" in model_lower:
            target = "gemini"

        # Check circuit breaker for target
        breaker = breakers.get(target)
        if breaker and breaker.state == "OPEN":
            # Fallback to backup
            fallback = self.backup if target == self.primary else self.primary
            logger.warning(
                f"Primary provider '{target}' circuit is OPEN. Failing over to '{fallback}'."
            )
            return fallback

        return target


class LLMProviderRouter(LLMProvider):
    def __init__(
        self,
        providers: Dict[str, LLMProvider],
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

    def get_circuit_breaker(self, provider_key: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(provider_key)

    async def generate(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Optional[str] = None,
    ) -> ProviderResponse:
        provider_key = self._policy.select_provider_key(model, self._providers, self._breakers)
        provider = self._providers[provider_key]
        breaker = self._breakers[provider_key]

        # Use fallback model name for backup if we failed over
        actual_model = model
        if provider_key == "openai" and "gemini" in model:
            actual_model = "gpt-4o-mini"  # Default backup model
        elif provider_key == "gemini" and "gpt" in model:
            actual_model = "gemini-1.5-flash"  # Default backup model

        logger.info(f"Routing generate request to provider: {provider_key} (Model: {actual_model})")
        
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
            fallback_key = "openai" if provider_key == "gemini" else "gemini"
            if fallback_key in self._providers:
                fallback_provider = self._providers[fallback_key]
                fallback_model = "gpt-4o-mini" if fallback_key == "openai" else "gemini-1.5-flash"
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
                    logger.critical(f"Fallback provider {fallback_key} also failed: {ex}")
                    raise ex
            raise e

    async def stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        provider_key = self._policy.select_provider_key(model, self._providers, self._breakers)
        provider = self._providers[provider_key]
        breaker = self._breakers[provider_key]

        actual_model = model
        if provider_key == "openai" and "gemini" in model:
            actual_model = "gpt-4o-mini"
        elif provider_key == "gemini" and "gpt" in model:
            actual_model = "gemini-1.5-flash"

        logger.info(f"Routing stream request to provider: {provider_key} (Model: {actual_model})")

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
