import logging
from typing import Any

from app.documents.domain.interfaces import FusionEngine
from app.documents.domain.models import RetrievedChunk

logger = logging.getLogger(__name__)


class ReciprocalRankFusionEngine(FusionEngine):
    """
    Standard Reciprocal Rank Fusion Engine (Phase 2.3 implementation).
    Direct baseline path used when ENABLE_WEIGHTED_RRF=False.
    """

    def __init__(self, rrf_k: int = 60) -> None:
        self.rrf_k = rrf_k

    def fuse(
        self,
        dense_results: list[RetrievedChunk],
        sparse_results: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        # Track ranks (1-indexed)
        dense_ranks = {
            chunk.chunk_id: idx + 1 for idx, chunk in enumerate(dense_results)
        }
        sparse_ranks = {
            chunk.chunk_id: idx + 1 for idx, chunk in enumerate(sparse_results)
        }

        # Collect all unique chunks
        chunk_map = {}
        for chunk in dense_results:
            chunk_map[chunk.chunk_id] = chunk
        for chunk in sparse_results:
            chunk_map[chunk.chunk_id] = chunk

        if not chunk_map:
            return []

        # Calculate RRF scores
        rrf_scores = {}
        for chunk_id in chunk_map:
            score = 0.0
            if chunk_id in dense_ranks:
                score += 1.0 / (dense_ranks[chunk_id] + self.rrf_k)
            if chunk_id in sparse_ranks:
                score += 1.0 / (sparse_ranks[chunk_id] + self.rrf_k)
            rrf_scores[chunk_id] = score

        # Sort chunks by RRF score descending
        sorted_chunk_ids = sorted(
            rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
        )

        fused_chunks = []
        for chunk_id in sorted_chunk_ids:
            orig_chunk = chunk_map[chunk_id]
            rrf_score = rrf_scores[chunk_id]

            fused_chunks.append(
                RetrievedChunk(
                    chunk_id=orig_chunk.chunk_id,
                    document_id=orig_chunk.document_id,
                    document_name=orig_chunk.document_name,
                    text=orig_chunk.text,
                    similarity_score=rrf_score,
                    normalized_score=None,
                    metadata=orig_chunk.metadata,
                    chunk_index=orig_chunk.chunk_index,
                )
            )

        return fused_chunks


class WeightedReciprocalRankFusionEngine(FusionEngine):
    """
    Weighted Reciprocal Rank Fusion Engine (Phase 2.4).
    Calculates: score(d) = sum_j (w_j / (k + rank_j(d)))
    When all weights are 1.0, this is mathematically identical to standard RRF.
    """

    def __init__(
        self,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> None:
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def fuse(
        self,
        dense_results: list[RetrievedChunk],
        sparse_results: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        return self.fuse_weighted(
            [
                (dense_results, self.dense_weight),
                (sparse_results, self.sparse_weight),
            ]
        )

    def fuse_weighted(
        self,
        result_lists_with_weights: list[tuple[list[RetrievedChunk], float]],
    ) -> list[RetrievedChunk]:
        chunk_map: dict[Any, RetrievedChunk] = {}
        rrf_scores: dict[Any, float] = {}
        sources_map: dict[Any, list[str]] = {}

        for list_idx, (chunks, weight) in enumerate(result_lists_with_weights):
            if weight <= 0.0:
                continue
            for rank_0, chunk in enumerate(chunks):
                cid = chunk.chunk_id
                rank_1 = rank_0 + 1
                if cid not in chunk_map:
                    chunk_map[cid] = chunk
                    rrf_scores[cid] = 0.0
                    sources_map[cid] = []

                rrf_scores[cid] += weight / (rank_1 + self.rrf_k)
                source_label = chunk.metadata.get(
                    "retrieval_source", f"source_{list_idx}"
                )
                if source_label not in sources_map[cid]:
                    sources_map[cid].append(source_label)

        if not chunk_map:
            return []

        sorted_chunk_ids = sorted(
            rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
        )

        fused_chunks = []
        for chunk_id in sorted_chunk_ids:
            orig_chunk = chunk_map[chunk_id]
            rrf_score = rrf_scores[chunk_id]
            merged_metadata = dict(orig_chunk.metadata)
            merged_metadata["rrf_score"] = rrf_score
            merged_metadata["retrieval_sources"] = sources_map[chunk_id]

            fused_chunks.append(
                RetrievedChunk(
                    chunk_id=orig_chunk.chunk_id,
                    document_id=orig_chunk.document_id,
                    document_name=orig_chunk.document_name,
                    text=orig_chunk.text,
                    similarity_score=rrf_score,
                    normalized_score=None,
                    metadata=merged_metadata,
                    chunk_index=orig_chunk.chunk_index,
                )
            )

        return fused_chunks
