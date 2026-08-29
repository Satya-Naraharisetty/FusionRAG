import hashlib
import math
from typing import Any

import httpx

from app.core.config import settings
from app.documents.domain.interfaces import TextEmbeddingProvider


class MockTextEmbeddingProvider(TextEmbeddingProvider):
    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    async def embed_text(self, text: str, model: str | None = None) -> list[float]:
        return self._generate_deterministic_vector(text)

    async def embed_batch(
        self, texts: list[str], model: str | None = None
    ) -> list[list[float]]:
        return [self._generate_deterministic_vector(t) for t in texts]

    def _generate_deterministic_vector(self, text: str) -> list[float]:
        # Generate deterministic float vector from SHA-256 hash
        hash_digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = []
        for i in range(self.dimensions):
            byte_val = hash_digest[i % len(hash_digest)]
            val = (byte_val / 255.0) * 2.0 - 1.0 + math.sin(i + (byte_val % 10))
            vector.append(val)
        # Normalize to unit length for cosine similarity
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


class JinaTextEmbeddingProvider(TextEmbeddingProvider):
    """
    Jina AI Bi-Encoder implementation for Dense Embeddings.
    Queries the Jina Embeddings API (https://api.jina.ai/v1/embeddings).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "jina-embeddings-v3",
        dimensions: int = 768,
        task: str = "retrieval.passage",
    ) -> None:
        self.api_key = api_key or getattr(settings, "JINA_API_KEY", "")
        self.model = model
        self.dimensions = dimensions
        self.task = task

    async def embed_text(self, text: str, model: str | None = None) -> list[float]:
        results = await self.embed_batch([text], model=model)
        return results[0]

    async def embed_batch(
        self, texts: list[str], model: str | None = None
    ) -> list[list[float]]:
        if not self.api_key or self.api_key.startswith("mock_"):
            mock_provider = MockTextEmbeddingProvider(dimensions=self.dimensions)
            return await mock_provider.embed_batch(texts, model=model)

        if not texts:
            return []

        url = "https://api.jina.ai/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model or self.model,
            "dimensions": self.dimensions,
            "input": texts,
            "task": self.task,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]
            return embeddings


def get_text_embedding_provider(
    provider_name: str = "jina",
    api_key: str | None = None,
    dimensions: int = 768,
) -> TextEmbeddingProvider:
    provider_lower = provider_name.lower()
    if provider_lower == "mock":
        return MockTextEmbeddingProvider(dimensions=dimensions)
    else:
        return JinaTextEmbeddingProvider(api_key=api_key, dimensions=dimensions)
