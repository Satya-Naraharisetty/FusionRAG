import logging

from app.chat.domain.interfaces import TokenEstimator
from app.chat.domain.models import GroundedContext
from app.documents.domain.models import RetrievedChunk
from app.documents.services.context_selector import ContextSelector

logger = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(
        self,
        token_estimator: TokenEstimator,
        max_context_tokens: int,
        context_selector: ContextSelector | None = None,
        enable_context_selection: bool | None = None,
    ) -> None:
        from app.core.config import settings

        self.token_estimator = token_estimator
        self.max_context_tokens = max_context_tokens
        self._enable_context_selection = (
            enable_context_selection
            if enable_context_selection is not None
            else getattr(settings, "ENABLE_CONTEXT_SELECTION", True)
        )
        self._context_selector = context_selector

    def build_context(self, chunks: list[RetrievedChunk]) -> GroundedContext:
        """
        Deduplicates chunks, formats them with doc boundaries and sequential renumbering,
        and truncates at chunk boundaries to stay within the MAX_CONTEXT_TOKENS budget.
        When context selection is enabled, utilizes ContextSelector score thresholds and ordering.
        When context selection is disabled or unavailable, follows the exact Phase 2.3 baseline path.
        """
        if self._enable_context_selection and self._context_selector is not None:
            # Score filter & sort chunks synchronously via context selector helper
            filtered = [
                c
                for c in chunks
                if self._context_selector._get_target_score(c)
                >= self._context_selector.min_chunk_score
            ]
            seen = set()
            deduped = []
            for c in filtered:
                if c.chunk_id not in seen:
                    seen.add(c.chunk_id)
                    deduped.append(c)
            chunks_to_format = self._context_selector._sort_chunks(
                deduped[: self._context_selector.max_chunks]
            )
        else:
            # Baseline Path (exact Phase 2.3 implementation)
            seen_chunk_ids = set()
            unique_chunks: list[RetrievedChunk] = []
            for chunk in chunks:
                if chunk.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.chunk_id)
                    unique_chunks.append(chunk)
            chunks_to_format = unique_chunks

        # Add chunks to context and renumber them sequentially (1-based)
        chunk_references: list[RetrievedChunk] = []
        concatenated_parts: list[str] = []
        accumulated_tokens = 0

        for chunk in chunks_to_format:
            new_idx = len(chunk_references) + 1
            formatted_chunk = (
                f"[Chunk {new_idx}] Document: {chunk.document_name} (ID: {chunk.document_id})\n"
                f"{chunk.text.strip()}\n\n"
            )

            chunk_tokens = self.token_estimator.estimate(formatted_chunk)

            # Check if this chunk exceeds the remaining context tokens budget
            if accumulated_tokens + chunk_tokens > self.max_context_tokens:
                logger.info(
                    f"Truncating context: Chunk {chunk.chunk_id} (token cost {chunk_tokens}) "
                    f"exceeds remaining budget ({self.max_context_tokens - accumulated_tokens} tokens)."
                )
                break

            concatenated_parts.append(formatted_chunk)
            chunk_references.append(chunk)
            accumulated_tokens += chunk_tokens

        concatenated_context = "".join(concatenated_parts).strip()

        return GroundedContext(
            concatenated_context=concatenated_context,
            chunk_references=chunk_references,
            token_estimate=accumulated_tokens,
        )

    async def build_context_async(
        self,
        chunks: list[RetrievedChunk],
        allowed_doc_ids: set | None = None,
    ) -> GroundedContext:
        """Asynchronous context builder utilizing ContextSelector when enabled."""
        if self._enable_context_selection and self._context_selector is not None:
            selected = await self._context_selector.select_context(
                chunks, allowed_doc_ids=allowed_doc_ids
            )
            return GroundedContext(
                concatenated_context=selected.concatenated_context,
                chunk_references=selected.selected_chunks,
                token_estimate=selected.token_count,
            )
        return self.build_context(chunks)
