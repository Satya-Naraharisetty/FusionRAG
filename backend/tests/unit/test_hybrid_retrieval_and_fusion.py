from uuid import UUID

from app.documents.domain.models import (
    CanonicalIdentity,
    EvidenceItem,
    EvidenceType,
)
from app.documents.services.fusion import (
    Hybrid4ChannelRRFEngine,
)


def test_hybrid_4_channel_rrf_mathematical_formula():
    engine = Hybrid4ChannelRRFEngine()
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    doc_id = UUID("22222222-2222-2222-2222-222222222222")
    elem_id = UUID("33333333-3333-3333-3333-333333333333")
    canon_id: CanonicalIdentity = (doc_id, 1, elem_id)

    ev_item = EvidenceItem(
        evidence_id=elem_id,
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc_id,
        document_version=1,
        element_id=elem_id,
        content="Test content",
    )

    # Rank 1 in DENSE (w=1.0), rank 1 in GRAPH (w=1.2)
    dense = [(canon_id, ev_item)]
    graph = [(canon_id, ev_item)]

    results = engine.fuse_4_channels(
        dense_candidates=dense,
        sparse_candidates=[],
        visual_candidates=[],
        graph_candidates=graph,
    )

    assert len(results) == 1
    cand = results[0]
    expected_score = (1.0 / (1 + 60)) + (1.2 / (1 + 60))  # 1.0/61 + 1.2/61 = 2.2 / 61
    assert abs(cand.fused_score - expected_score) < 1e-6
    assert cand.channel_ranks["DENSE"] == 1
    assert cand.channel_ranks["GRAPH"] == 1
    assert "SPARSE" not in cand.channel_ranks


def test_hybrid_4_channel_channel_local_deduplication():
    engine = Hybrid4ChannelRRFEngine()
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    doc_id = UUID("22222222-2222-2222-2222-222222222222")
    elem_id = UUID("33333333-3333-3333-3333-333333333333")
    canon_id: CanonicalIdentity = (doc_id, 1, elem_id)

    ev_item = EvidenceItem(
        evidence_id=elem_id,
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc_id,
        document_version=1,
        element_id=elem_id,
        content="Test content",
    )

    # Candidate appears at rank 1 and rank 3 in same channel
    dense = [(canon_id, ev_item), (canon_id, ev_item)]

    results = engine.fuse_4_channels(
        dense_candidates=dense,
        sparse_candidates=[],
        visual_candidates=[],
        graph_candidates=[],
    )

    assert len(results) == 1
    # Should only count rank 1
    expected_score = 1.0 / (1 + 60)
    assert abs(results[0].fused_score - expected_score) < 1e-6


def test_hybrid_4_channel_deterministic_tie_breaking():
    engine = Hybrid4ChannelRRFEngine()
    user_id = UUID("11111111-1111-1111-1111-111111111111")

    # Two candidates with identical scores
    doc1 = UUID("00000000-0000-0000-0000-000000000001")
    doc2 = UUID("00000000-0000-0000-0000-000000000002")
    elem1 = UUID("00000000-0000-0000-0000-00000000000a")
    elem2 = UUID("00000000-0000-0000-0000-00000000000b")

    ev1 = EvidenceItem(
        evidence_id=elem1,
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc1,
        document_version=1,
        element_id=elem1,
        content="Item 1",
    )
    ev2 = EvidenceItem(
        evidence_id=elem2,
        evidence_type=EvidenceType.TEXT_CHUNK,
        user_id=user_id,
        document_id=doc2,
        document_version=1,
        element_id=elem2,
        content="Item 2",
    )

    # In dense: (doc2, 1, elem2) is rank 1, in sparse: (doc1, 1, elem1) is rank 1
    # dense weight=1.0, sparse weight=0.8 -> score(doc2) = 1.0/61, score(doc1) = 0.8/61 -> doc2 > doc1
    results = engine.fuse_4_channels(
        dense_candidates=[((doc2, 1, elem2), ev2)],
        sparse_candidates=[((doc1, 1, elem1), ev1)],
        visual_candidates=[],
        graph_candidates=[],
    )

    assert results[0].document_id == doc2
    assert results[1].document_id == doc1
