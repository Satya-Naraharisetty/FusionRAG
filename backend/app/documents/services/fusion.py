from app.documents.domain.interfaces import FusionEngine
from app.documents.domain.models import RetrievedChunk


class ReciprocalRankFusionEngine(FusionEngine):
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

            # Create a new RetrievedChunk with RRF score as similarity_score, normalized_score = None
            fused_chunks.append(
                RetrievedChunk(
                    chunk_id=orig_chunk.chunk_id,
                    document_id=orig_chunk.document_id,
                    document_name=orig_chunk.document_name,
                    text=orig_chunk.text,
                    similarity_score=rrf_score,
                    normalized_score=None,  # No normalization for RRF scores per architecture requirements
                    metadata=orig_chunk.metadata,
                    chunk_index=orig_chunk.chunk_index,
                )
            )

        return fused_chunks
