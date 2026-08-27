import logging
import time
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
        from app.core.telemetry import (
            LLM_CIRCUIT_BREAKER_STATE,
            LLM_DURATION,
            LLM_REQUESTS,
            LLM_TOKENS,
            get_tracer,
        )

        tracer = get_tracer("hybrid-rag.llm")

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

        # Update circuit breaker state metric
        try:
            state_val = getattr(breaker, "state", None)
            if state_val:
                st_name = getattr(state_val, "value", str(state_val)).lower()
                LLM_CIRCUIT_BREAKER_STATE.labels(
                    provider=provider_key, state=st_name
                ).set(1.0)
        except Exception:
            pass

        t0 = time.perf_counter()
        with tracer.start_as_current_span("llm.provider.generate") as span:
            span.set_attribute("llm.provider", provider_key)
            span.set_attribute("llm.model", actual_model)
            try:
                resp = await breaker.call(
                    provider.generate,
                    messages=messages,
                    model=actual_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                dur = time.perf_counter() - t0
                try:
                    LLM_DURATION.labels(
                        provider=provider_key, model=actual_model
                    ).observe(dur)
                    LLM_REQUESTS.labels(
                        provider=provider_key, model=actual_model, status="success"
                    ).inc()
                    if resp.usage:
                        if resp.usage.prompt_tokens:
                            LLM_TOKENS.labels(
                                provider=provider_key, model=actual_model, type="prompt"
                            ).inc(resp.usage.prompt_tokens)
                        if resp.usage.completion_tokens:
                            LLM_TOKENS.labels(
                                provider=provider_key,
                                model=actual_model,
                                type="completion",
                            ).inc(resp.usage.completion_tokens)
                except Exception:
                    pass
                return resp
            except Exception as e:
                dur = time.perf_counter() - t0
                try:
                    LLM_REQUESTS.labels(
                        provider=provider_key, model=actual_model, status="error"
                    ).inc()
                except Exception:
                    pass
                span.record_exception(e)
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
                    with tracer.start_as_current_span(
                        "llm.provider.fallback"
                    ) as fb_span:
                        fb_span.set_attribute("llm.provider", fallback_key)
                        fb_span.set_attribute("llm.model", fallback_model)
                        t_fb = time.perf_counter()
                        try:
                            fb_resp = await fallback_provider.generate(
                                messages=messages,
                                model=fallback_model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                tools=tools,
                                tool_choice=tool_choice,
                            )
                            fb_dur = time.perf_counter() - t_fb
                            try:
                                LLM_DURATION.labels(
                                    provider=fallback_key, model=fallback_model
                                ).observe(fb_dur)
                                LLM_REQUESTS.labels(
                                    provider=fallback_key,
                                    model=fallback_model,
                                    status="success",
                                ).inc()
                                if fb_resp.usage:
                                    if fb_resp.usage.prompt_tokens:
                                        LLM_TOKENS.labels(
                                            provider=fallback_key,
                                            model=fallback_model,
                                            type="prompt",
                                        ).inc(fb_resp.usage.prompt_tokens)
                                    if fb_resp.usage.completion_tokens:
                                        LLM_TOKENS.labels(
                                            provider=fallback_key,
                                            model=fallback_model,
                                            type="completion",
                                        ).inc(fb_resp.usage.completion_tokens)
                            except Exception:
                                pass
                            return fb_resp
                        except Exception as ex:
                            try:
                                LLM_REQUESTS.labels(
                                    provider=fallback_key,
                                    model=fallback_model,
                                    status="error",
                                ).inc()
                            except Exception:
                                pass
                            fb_span.record_exception(ex)
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
        from app.core.telemetry import (
            LLM_CIRCUIT_BREAKER_STATE,
            LLM_DURATION,
            LLM_REQUESTS,
            LLM_TIME_TO_FIRST_TOKEN,
            LLM_TOKENS,
            get_tracer,
        )

        tracer = get_tracer("hybrid-rag.llm")

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

        try:
            state_val = getattr(breaker, "state", None)
            if state_val:
                st_name = getattr(state_val, "value", str(state_val)).lower()
                LLM_CIRCUIT_BREAKER_STATE.labels(
                    provider=provider_key, state=st_name
                ).set(1.0)
        except Exception:
            pass

        # Verify circuit status before stream starts
        await breaker.check_state()

        start_time = time.perf_counter()
        first_token_recorded = False

        with tracer.start_as_current_span("llm.provider.stream") as span:
            span.set_attribute("llm.provider", provider_key)
            span.set_attribute("llm.model", actual_model)
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
                    if not first_token_recorded and (
                        chunk.text_delta or chunk.tool_calls
                    ):
                        ttft = time.perf_counter() - start_time
                        span.set_attribute("llm.ttft_seconds", ttft)
                        try:
                            LLM_TIME_TO_FIRST_TOKEN.labels(
                                provider=provider_key, model=actual_model
                            ).observe(ttft)
                        except Exception:
                            pass
                        first_token_recorded = True

                    if chunk.usage:
                        try:
                            if chunk.usage.prompt_tokens:
                                LLM_TOKENS.labels(
                                    provider=provider_key,
                                    model=actual_model,
                                    type="prompt",
                                ).inc(chunk.usage.prompt_tokens)
                            if chunk.usage.completion_tokens:
                                LLM_TOKENS.labels(
                                    provider=provider_key,
                                    model=actual_model,
                                    type="completion",
                                ).inc(chunk.usage.completion_tokens)
                        except Exception:
                            pass

                    yield chunk

                total_dur = time.perf_counter() - start_time
                span.set_attribute("llm.duration_seconds", total_dur)
                try:
                    LLM_DURATION.labels(
                        provider=provider_key, model=actual_model
                    ).observe(total_dur)
                    LLM_REQUESTS.labels(
                        provider=provider_key, model=actual_model, status="success"
                    ).inc()
                except Exception:
                    pass
                await breaker.record_success()
            except Exception as e:
                span.record_exception(e)
                try:
                    LLM_REQUESTS.labels(
                        provider=provider_key, model=actual_model, status="error"
                    ).inc()
                except Exception:
                    pass
                await breaker.record_failure()
                logger.error(f"Streaming failed on provider {provider_key}: {e}")
                raise e
