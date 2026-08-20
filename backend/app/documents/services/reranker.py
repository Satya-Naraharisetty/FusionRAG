import asyncio
import logging
import threading
from typing import Any

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


class CrossEncoderReranker(Reranker):
    """
    Production-grade Cross-Encoder Reranker using sentence-transformers.
    Performs full cross-attention query-document relevance scoring on candidate chunks.

    Architecture & Safety:
    - Thread-safe singleton model lifecycle.
    - Synchronous PyTorch inference offloaded via asyncio.to_thread to avoid blocking event loop.
    - Request-level concurrency bounded via asyncio.Semaphore.
    - Graceful fallback to incoming MMR candidate order on initialization or inference errors.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        batch_size: int = 16,
        max_length: int = 512,
        concurrency_limit: int = 4,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._concurrency_limit = concurrency_limit

        self._model: Any = None
        self._init_lock = threading.Lock()
        self._init_failed: bool = False
        self._init_error: str | None = None
        self._semaphore: asyncio.Semaphore | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        """
        Lifecycle-safe lazy semaphore initialization tied to the running event loop.
        Avoids binding to loop at arbitrary module import time.
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency_limit)
        return self._semaphore

    def ensure_model_loaded(self) -> None:
        """
        Thread-safe model initialization. Can be called at application startup
        to pre-warm the model, or on-demand on first request.
        """
        if self._model is not None:
            return
        if self._init_failed:
            raise RuntimeError(
                f"Cross-encoder model initialization previously failed: {self._init_error}"
            )

        with self._init_lock:
            if self._model is not None:
                return
            if self._init_failed:
                raise RuntimeError(
                    f"Cross-encoder model initialization previously failed: {self._init_error}"
                )
            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    f"Initializing CrossEncoder model '{self._model_name}' on device '{self._device}'..."
                )
                self._model = CrossEncoder(
                    self._model_name,
                    device=self._device,
                    max_length=self._max_length,
                )
                logger.info("CrossEncoder model successfully loaded and ready.")
            except Exception as e:
                self._init_failed = True
                self._init_error = str(e)
                logger.critical(
                    f"Failed to load CrossEncoder model '{self._model_name}': {e}",
                    exc_info=True,
                )
                raise

    def _predict_scores(self, query: str, texts: list[str]) -> list[float]:
        self.ensure_model_loaded()
        pairs = [(query, text) for text in texts]
        raw_scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return [float(s) for s in raw_scores]

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        # 1. 0 candidates -> return empty list
        if not chunks:
            return []

        # 2. Check model readiness / handle initialization failure
        try:
            self.ensure_model_loaded()
        except Exception as init_err:
            logger.warning(
                f"Cross-encoder reranker unavailable ({init_err}); falling back to incoming MMR candidate order."
            )
            return chunks

        # 3. Score candidates with bounded async concurrency
        try:
            semaphore = self._get_semaphore()
            async with semaphore:
                texts = [c.text for c in chunks]
                scores = await asyncio.to_thread(self._predict_scores, query, texts)

            # 4. Handle 1 candidate -> assign score, no reordering necessary
            if len(chunks) == 1:
                return [chunks[0].model_copy(update={"rerank_score": scores[0]})]

            # 5. Handle N candidates -> assign score, sort descending
            scored_chunks: list[tuple[float, RetrievedChunk]] = []
            for score, chunk in zip(scores, chunks, strict=True):
                updated_chunk = chunk.model_copy(update={"rerank_score": score})
                scored_chunks.append((score, updated_chunk))

            # Stable sort descending (preserves incoming MMR order for identical scores)
            scored_chunks.sort(key=lambda item: item[0], reverse=True)
            return [chunk for _, chunk in scored_chunks]

        except Exception as inf_err:
            logger.error(
                f"Cross-encoder inference failed during reranking: {inf_err}. Falling back to MMR order.",
                exc_info=True,
            )
            return chunks
