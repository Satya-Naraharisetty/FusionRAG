from uuid import uuid4

import pytest

from app.documents.domain.models import RetrievedChunk, SearchResult
from app.documents.services.query_classifier import DeterministicQueryClassifier
from app.documents.services.query_decomposer import DeterministicQueryDecomposer
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.rag.orchestration.evidence_evaluator import EvidenceSufficiencyEvaluator
from app.rag.orchestration.master import AdaptiveRAGOrchestrator
from app.rag.orchestration.replanner import Replanner
from app.rag.orchestration.strategy_router import RetrievalStrategyRouter
from app.rag.orchestration.telemetry import OrchestrationTelemetry


def test_golden_v3_dataset_loader():
    loader = DatasetLoader()
    dataset = loader.load_dataset(
        file_path="app/evaluation/datasets/golden/golden_v3.yaml",
        dataset_id="golden_rag_dataset",
        version="3.0.0",
    )
    assert dataset.version == "3.0.0"
    assert len(dataset.samples) >= 80

    # Verify presence of HyDE-positive and negative samples
    categories = [s.category for s in dataset.samples]
    assert any("hyde" in cat for cat in categories)
    assert any("factual" in cat for cat in categories)
    assert any("decomposition" in cat or "multi_hop" in cat for cat in categories)


@pytest.mark.asyncio
async def test_adaptive_rag_e2e_orchestration_flow():
    from unittest.mock import AsyncMock, MagicMock

    user_id = uuid4()
    doc_id = uuid4()

    sample_chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="cloud_architecture.md",
            chunk_index=0,
            text="Data at rest: Persistent storage is encrypted with AWS KMS CMK using AES-256-GCM.",
            similarity_score=0.92,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="cloud_architecture.md",
            chunk_index=1,
            text="Disaster recovery: Recovery Point Objective (RPO) is 5 minutes and RTO is 30 minutes.",
            similarity_score=0.89,
        ),
    ]

    mock_retrieval = MagicMock()
    mock_retrieval.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="multi-hop query",
            retrieval_time=0.03,
            total_matches=2,
            retrieved_chunks=sample_chunks,
            dense_matches=sample_chunks,
            sparse_matches=[],
        )
    )

    classifier = DeterministicQueryClassifier()
    orchestrator = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3),
        replanner=Replanner(),
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        telemetry=OrchestrationTelemetry(),
        max_iterations=3,
    )

    result = await orchestrator.orchestrate(
        query="What encryption protects data at rest and what is the disaster recovery RPO target?",
        user_id=user_id,
        top_k=5,
    )

    assert len(result.retrieved_chunks) == 2
    assert result.diagnostics is not None
    assert result.diagnostics["final_status"] in ("success", "partial")
    assert result.diagnostics["evidence_sufficiency"] is True
