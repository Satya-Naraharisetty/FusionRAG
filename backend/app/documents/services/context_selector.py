import logging
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.chat.domain.interfaces import TokenEstimator
from app.documents.domain.interfaces import ChunkRepository
from app.documents.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)


class SelectedContext(BaseModel):
    concatenated_context: str
    selected_chunks: list[RetrievedChunk]
    token_count: int
    truncated: bool = False
    original_chunk_count: int = 0
    final_chunk_count: int = 0
    neighbor_chunks_added: int = 0

    model_config = ConfigDict(frozen=True)


class ContextSelector:
    """
    ContextSelector enforces relevance thresholds, deterministic ordering,
    optional post-reranking neighbor chunk expansion, deduplication,
    and strict token budgets.
    """

    def __init__(
        self,
        token_estimator: TokenEstimator,
        max_context_tokens: int = 6000,
        max_chunks: int = 12,
        min_chunk_score: float = 0.0,
        score_source: Literal[
            "rerank_score", "rrf_score", "similarity_score"
        ] = "rerank_score",
        ordering_strategy: str = "rerank_score_desc",
        enable_neighbor_chunks: bool = False,
        neighbor_window: int = 1,
        chunk_repo: ChunkRepository | None = None,
    ) -> None:
        self.token_estimator = token_estimator
        self.max_context_tokens = max_context_tokens
        self.max_chunks = max_chunks
        self.min_chunk_score = min_chunk_score
        self.score_source = score_source
        self.ordering_strategy = ordering_strategy
        self.enable_neighbor_chunks = enable_neighbor_chunks
        self.neighbor_window = max(1, neighbor_window)
        self.chunk_repo = chunk_repo

    def _get_target_score(self, chunk: RetrievedChunk) -> float:
        if self.score_source == "rerank_score":
            return (
                chunk.rerank_score
                if chunk.rerank_score is not None
                else chunk.similarity_score
            )
        elif self.score_source == "rrf_score":
            return float(chunk.metadata.get("rrf_score", chunk.similarity_score))
        else:  # similarity_score
            return chunk.similarity_score

    async def _expand_neighbors(
        self,
        chunks: list[RetrievedChunk],
        allowed_doc_ids: set[UUID] | None = None,
    ) -> tuple[list[RetrievedChunk], int]:
        if not self.enable_neighbor_chunks or not self.chunk_repo:
            return chunks, 0

        neighbors_added = 0
        expanded_list: list[RetrievedChunk] = []
        seen_ids = {c.chunk_id for c in chunks}

        for chunk in chunks:
            expanded_list.append(chunk)

            # Security verification: document must be in allowed scope
            if allowed_doc_ids is not None and chunk.document_id not in allowed_doc_ids:
                continue

            # Fetch adjacent chunk indices
            doc_id = chunk.document_id
            current_idx = chunk.chunk_index
            target_indices = []
            for offset in range(-self.neighbor_window, self.neighbor_window + 1):
                if offset != 0 and (current_idx + offset) >= 0:
                    target_indices.append(current_idx + offset)

            if not target_indices:
                continue

            try:
                # Query chunks by document_id and index
                if hasattr(self.chunk_repo, "list_by_document"):
                    db_chunks = await self.chunk_repo.list_by_document(doc_id)
                elif hasattr(self.chunk_repo, "get_chunks_by_document"):
                    db_chunks = await self.chunk_repo.get_chunks_by_document(doc_id)
                else:
                    db_chunks = []
                for db_chunk in db_chunks:
                    if (
                        db_chunk.chunk_index in target_indices
                        and db_chunk.id not in seen_ids
                    ):
                        seen_ids.add(db_chunk.id)
                        # Inherit baseline score slightly attenuated for neighbor
                        base_score = self._get_target_score(chunk) * 0.9
                        neighbor_retrieved = RetrievedChunk(
                            chunk_id=db_chunk.id,
                            document_id=db_chunk.document_id,
                            document_name=chunk.document_name,
                            text=db_chunk.text,
                            similarity_score=chunk.similarity_score * 0.9,
                            normalized_score=None,
                            rerank_score=base_score
                            if chunk.rerank_score is not None
                            else None,
                            metadata={
                                **db_chunk.metadata,
                                "is_neighbor": True,
                                "parent_chunk_id": str(chunk.chunk_id),
                                "source_document": chunk.document_name,
                            },
                            chunk_index=db_chunk.chunk_index,
                        )
                        expanded_list.append(neighbor_retrieved)
                        neighbors_added += 1
            except Exception as e:
                logger.warning(f"Neighbor chunk expansion failed for doc {doc_id}: {e}")

        return expanded_list, neighbors_added

    def _sort_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        def sort_key(c: RetrievedChunk) -> tuple[float, float, str, int]:
            score = self._get_target_score(c)
            sim_score = c.similarity_score
            doc_id_str = str(c.document_id)
            chunk_idx = c.chunk_index
            # Descending scores (negated for tuple), ascending tie-breaker for doc/idx
            return (-score, -sim_score, doc_id_str, chunk_idx)

        return sorted(chunks, key=sort_key)

    async def select_context(
        self,
        chunks: list[RetrievedChunk],
        allowed_doc_ids: set[UUID] | None = None,
    ) -> SelectedContext:
        original_count = len(chunks)
        if not chunks:
            return SelectedContext(
                concatenated_context="",
                selected_chunks=[],
                token_count=0,
                truncated=False,
                original_chunk_count=0,
                final_chunk_count=0,
                neighbor_chunks_added=0,
            )

        # 1. Score threshold filtering
        filtered_chunks: list[RetrievedChunk] = []
        for c in chunks:
            score = self._get_target_score(c)
            if score >= self.min_chunk_score:
                filtered_chunks.append(c)

        # 2. Deduplication by chunk_id
        seen_ids = set()
        unique_chunks: list[RetrievedChunk] = []
        for c in filtered_chunks:
            if c.chunk_id not in seen_ids:
                seen_ids.add(c.chunk_id)
                unique_chunks.append(c)

        # 3. Post-Rerank Neighbor Expansion (if enabled)
        expanded_chunks, neighbors_added = await self._expand_neighbors(
            unique_chunks[: self.max_chunks], allowed_doc_ids=allowed_doc_ids
        )

        # 4. Context Ordering
        ordered_chunks = self._sort_chunks(expanded_chunks)

        # 5. Token Budget Enforcement & Truncation
        final_chunks: list[RetrievedChunk] = []
        concatenated_parts: list[str] = []
        accumulated_tokens = 0
        truncated = False

        for chunk in ordered_chunks:
            if len(final_chunks) >= self.max_chunks:
                truncated = True
                break

            idx = len(final_chunks) + 1
            formatted_chunk = (
                f"[Chunk {idx}] Document: {chunk.document_name} (ID: {chunk.document_id})\n"
                f"{chunk.text.strip()}\n\n"
            )
            chunk_tokens = self.token_estimator.estimate(formatted_chunk)

            if accumulated_tokens + chunk_tokens > self.max_context_tokens:
                logger.info(
                    f"ContextSelector: Chunk {chunk.chunk_id} ({chunk_tokens} tokens) "
                    f"exceeds remaining token budget ({self.max_context_tokens - accumulated_tokens} remaining)."
                )
                truncated = True
                break

            concatenated_parts.append(formatted_chunk)
            final_chunks.append(chunk)
            accumulated_tokens += chunk_tokens

        concatenated_context = "".join(concatenated_parts).strip()

        return SelectedContext(
            concatenated_context=concatenated_context,
            selected_chunks=final_chunks,
            token_count=accumulated_tokens,
            truncated=truncated,
            original_chunk_count=original_count,
            final_chunk_count=len(final_chunks),
            neighbor_chunks_added=neighbors_added,
        )
