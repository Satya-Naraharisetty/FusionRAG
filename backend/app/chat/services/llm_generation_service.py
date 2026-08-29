import inspect
from collections.abc import AsyncIterator
from typing import Any

from app.chat.domain.interfaces import LLMProvider, ProviderResponse, StreamChunk
from app.chat.domain.models import ChatMessage


class LLMGenerationService:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        stop_sequences: list[str] | None = None,
        response_schema: dict | None = None,
        response_mime_type: str | None = None,
    ) -> ProviderResponse:
        """
        Generates completion response from LLM provider.
        """
        gen_fn = self.llm_provider.generate
        kwargs: dict[str, Any] = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        sig = inspect.signature(gen_fn)
        params = sig.parameters
        has_varkw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if "stop_sequences" in params or has_varkw:
            kwargs["stop_sequences"] = stop_sequences
        if "response_schema" in params or has_varkw:
            kwargs["response_schema"] = response_schema
        if "response_mime_type" in params or has_varkw:
            kwargs["response_mime_type"] = response_mime_type

        return await gen_fn(**kwargs)

    def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        stop_sequences: list[str] | None = None,
        response_schema: dict | None = None,
        response_mime_type: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streams completion responses from LLM provider.
        """
        stream_fn = self.llm_provider.stream
        kwargs: dict[str, Any] = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        sig = inspect.signature(stream_fn)
        params = sig.parameters
        has_varkw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if "stop_sequences" in params or has_varkw:
            kwargs["stop_sequences"] = stop_sequences
        if "response_schema" in params or has_varkw:
            kwargs["response_schema"] = response_schema
        if "response_mime_type" in params or has_varkw:
            kwargs["response_mime_type"] = response_mime_type

        return stream_fn(**kwargs)
