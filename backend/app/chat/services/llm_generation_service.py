from typing import AsyncIterator

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
    ) -> ProviderResponse:
        """
        Generates completion response from LLM provider.
        """
        return await self.llm_provider.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streams completion responses from LLM provider.
        """
        return self.llm_provider.stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
