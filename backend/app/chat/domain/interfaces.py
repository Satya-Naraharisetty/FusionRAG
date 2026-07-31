from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.chat.domain.models import ChatMessage, Usage


class TokenEstimator(ABC):
    @abstractmethod
    def estimate(self, text: str) -> int:
        """
        Estimate the number of tokens in the given text.
        """
        pass


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, Usage]:
        """
        Generate a complete response from the LLM.
        Returns a tuple of (generated_text, usage_metrics).
        """
        pass

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, Usage | None]]:
        """
        Stream the LLM response.
        Yields tuples of (text_delta, usage_metrics_at_end_or_none).
        """
        pass
