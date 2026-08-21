import asyncio
import logging

import httpx

from app.documents.domain.interfaces import Reranker
from app.documents.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)


class IdentityReranker(Reranker):
    """
    No-op reranker implementation returning chunks unchanged.
    Used when reranking is disabled or as a safe fallback.
    """

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        return chunks


class JinaCrossEncoderReranker(Reranker):
    """
    Production-grade API-based Cross-Encoder Reranker using Jina AI Rerank API.
    Performs full cross-attention query-document relevance scoring via Jina AI.

    Endpoint: https://api.jina.ai/v1/rerank
    Default model: jina-reranker-v2-base-multilingual

    Architecture & Safety:
    - Bounded timeouts & exponential retries on transient network/rate limit errors.
    - Zero local PyTorch/CUDA runtime dependency.
    - Concurrency bounding via asyncio.Semaphore.
    - Graceful fallback to incoming candidate order on missing API key, rate limits, or network errors.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "jina-reranker-v2-base-multilingual",
        timeout: float = 5.0,
        max_retries: int = 2,
        concurrency_limit: int = 8,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._timeout = timeout
        self._max_retries = max_retries
        self._concurrency_limit = concurrency_limit
        self._semaphore: asyncio.Semaphore | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency_limit)
        return self._semaphore

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []

        if not self._api_key or not self._api_key.strip():
            logger.warning(
                "JINA_API_KEY is not configured; falling back to incoming candidate order."
            )
            return chunks

        url = "https://api.jina.ai/v1/rerank"
        headers = {
            "Authorization": f"Bearer {self._api_key.strip()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model_name,
            "query": query,
            "documents": [c.text for c in chunks],
            "top_n": len(chunks),
        }

        semaphore = self._get_semaphore()
        for attempt in range(self._max_retries + 1):
            try:
                async with semaphore:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=self._timeout,
                        )
                        response.raise_for_status()
                        data = response.json()

                results = data.get("results", [])
                if not results:
                    return chunks

                scored_chunks: list[RetrievedChunk] = []
                for item in results:
                    idx = int(item["index"])
                    score = float(item["relevance_score"])
                    if 0 <= idx < len(chunks):
                        updated = chunks[idx].model_copy(update={"rerank_score": score})
                        scored_chunks.append(updated)

                if len(scored_chunks) < len(chunks):
                    seen_indices = {
                        int(item["index"])
                        for item in results
                        if 0 <= int(item["index"]) < len(chunks)
                    }
                    for i, chunk in enumerate(chunks):
                        if i not in seen_indices:
                            scored_chunks.append(chunk)

                return scored_chunks

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if (
                    status_code in (429, 500, 502, 503, 504)
                    and attempt < self._max_retries
                ):
                    await asyncio.sleep(2.0**attempt)
                    continue
                logger.warning(
                    f"Jina AI rerank HTTP {status_code} error: {e}. Falling back to incoming candidate order."
                )
                return chunks
            except Exception as e:
                if attempt < self._max_retries:
                    await asyncio.sleep(2.0**attempt)
                    continue
                logger.warning(
                    f"Jina AI rerank request failed ({e}); falling back to incoming candidate order."
                )
                return chunks

        return chunks


# Alias for backward compatibility
JinaReranker = JinaCrossEncoderReranker
