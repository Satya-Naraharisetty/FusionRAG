import uuid

from app.documents.domain.models import RetrievedChunk
from app.documents.services.fusion import (
    ReciprocalRankFusionEngine,
    WeightedReciprocalRankFusionEngine,
)


def _make_chunk(doc_name: str, score: float, rank_idx: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name=doc_name,
        text=f"Text for {doc_name} chunk {rank_idx}",
        similarity_score=score,
        normalized_score=score,
        metadata={"rank": rank_idx},
        chunk_index=rank_idx,
    )


def test_weighted_rrf_mathematical_equivalence_when_weights_equal_one():
    """
    CRITICAL TEST:
    Verifies that when dense_weight=1.0 and sparse_weight=1.0,
    WeightedReciprocalRankFusionEngine produces exact mathematical equivalence
    with standard ReciprocalRankFusionEngine.
    """
    c1 = _make_chunk("doc_a", 0.9, 0)
    c2 = _make_chunk("doc_b", 0.8, 1)
    c3 = _make_chunk("doc_c", 0.7, 2)

    dense_list = [c1, c2]
    sparse_list = [c2, c3]

    standard_engine = ReciprocalRankFusionEngine(rrf_k=60)
    weighted_engine = WeightedReciprocalRankFusionEngine(
        rrf_k=60, dense_weight=1.0, sparse_weight=1.0
    )

    standard_results = standard_engine.fuse(dense_list, sparse_list)
    weighted_results = weighted_engine.fuse(dense_list, sparse_list)

    assert len(standard_results) == len(weighted_results)

    for std_chunk, w_chunk in zip(standard_results, weighted_results, strict=True):
        assert std_chunk.chunk_id == w_chunk.chunk_id
        assert abs(std_chunk.similarity_score - w_chunk.similarity_score) < 1e-9


def test_weighted_rrf_dense_bias():
    c1 = _make_chunk("dense_top", 0.95, 0)
    c2 = _make_chunk("sparse_top", 0.95, 0)

    # Dense weight heavily favors dense results
    engine = WeightedReciprocalRankFusionEngine(
        rrf_k=60, dense_weight=3.0, sparse_weight=1.0
    )

    results = engine.fuse([c1], [c2])
    assert len(results) == 2
    assert results[0].chunk_id == c1.chunk_id
    assert results[0].similarity_score > results[1].similarity_score


def test_weighted_rrf_sparse_bias():
    c1 = _make_chunk("dense_top", 0.95, 0)
    c2 = _make_chunk("sparse_top", 0.95, 0)

    # Sparse weight heavily favors sparse results
    engine = WeightedReciprocalRankFusionEngine(
        rrf_k=60, dense_weight=1.0, sparse_weight=3.0
    )

    results = engine.fuse([c1], [c2])
    assert len(results) == 2
    assert results[0].chunk_id == c2.chunk_id
    assert results[0].similarity_score > results[1].similarity_score
