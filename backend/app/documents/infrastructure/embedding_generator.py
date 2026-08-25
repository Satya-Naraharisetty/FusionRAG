import asyncio
import logging
from typing import Any

import httpx

from app.documents.domain.interfaces import EmbeddingGenerator

logger = logging.getLogger(__name__)


class JinaEmbeddingGenerator(EmbeddingGenerator):
    """
    Jina AI Bi-Encoder implementation of the EmbeddingGenerator.
    Queries the Jina AI Embeddings API (https://api.jina.ai/v1/embeddings) via HTTP POST.
    Models: jina-embeddings-v3 (1024 / 768 dims), jina-embeddings-v2-base-en.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "jina-embeddings-v3",
        dimension: int = 768,
        task: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._task = task

    @property
    def dimension(self) -> int:
        return self._dimension

    async def generate(self, text: str, task: str | None = None) -> list[float]:
        results = await self.batch_generate(
            [text], task=task or self._task or "retrieval.query"
        )
        if not results:
            raise RuntimeError("Jina API failed to return embeddings.")
        return results[0]

    async def batch_generate(
        self, texts: list[str], task: str | None = None
    ) -> list[list[float]]:
        if not texts:
            return []

        url = "https://api.jina.ai/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "dimensions": self._dimension,
            "input": texts,
        }
        effective_task = task or self._task
        if effective_task and "v3" in self._model:
            payload["task"] = effective_task

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()

                    embeddings = [item["embedding"] for item in data.get("data", [])]

                    for i, emb in enumerate(embeddings):
                        if len(emb) != self._dimension:
                            raise ValueError(
                                f"Embedding dimension mismatch at index {i}: "
                                f"expected {self._dimension}, got {len(emb)}"
                            )

                    return embeddings
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < max_retries - 1
                ):
                    await asyncio.sleep(backoff_factor**attempt)
                    continue
                raise
            except httpx.RequestError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_factor**attempt)
                    continue
                raise

        raise RuntimeError("Jina embedding generation failed after all retry attempts.")
