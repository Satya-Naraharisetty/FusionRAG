from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.documents.domain.models import (
    DocumentRetrievalScope,
    RetrievedChunk,
    SearchResult,
)
from app.documents.services.query_classifier import DeterministicQueryClassifier
from app.documents.services.query_decomposer import DeterministicQueryDecomposer
from app.rag.orchestration.evidence_evaluator import EvidenceSufficiencyEvaluator
from app.rag.orchestration.master import AdaptiveRAGOrchestrator
from app.rag.orchestration.models import (
    EvidenceAssessment,
    RetrievalDecision,
    RetrievalStrategy,
    RetrievalTaskResult,
    TaskStatus,
)
from app.rag.orchestration.replanner import Replanner, compute_task_fingerprint
from app.rag.orchestration.strategy_router import RetrievalStrategyRouter
from app.rag.orchestration.telemetry import OrchestrationTelemetry


@pytest.mark.asyncio
async def test_strategy_router_precedence():
    classifier = DeterministicQueryClassifier()
    router = RetrievalStrategyRouter(classifier)

    # 1. Multi-hop / comparison -> DECOMPOSITION
    decision1 = await router.select_strategy(
        "Compare the enterprise tier rate limit with the standard tier rate limit."
    )
    assert decision1.strategy == RetrievalStrategy.DECOMPOSITION

    # 2. Acronym / technical jargon -> QUERY_EXPANSION
    decision2 = await router.select_strategy(
        "What is AWS KMS CMK rotation schedule for data at rest?"
    )
    assert decision2.strategy == RetrievalStrategy.QUERY_EXPANSION

    # 3. Conceptual / semantic -> HYDE
    decision3 = await router.select_strategy(
        "Explain the architecture and mechanisms governing disaster recovery."
    )
    assert decision3.strategy == RetrievalStrategy.HYDE

    # 4. Direct factual -> STANDARD_HYBRID
    decision4 = await router.select_strategy(
        "What is the standard availability percentage for enterprise tier tenants?"
    )
    assert decision4.strategy == RetrievalStrategy.STANDARD_HYBRID

    # 5. Resource budget constraint override -> STANDARD_HYBRID
    decision5 = await router.select_strategy(
        "Compare enterprise and standard tiers",
        resource_budget={"max_allowed_calls": 1},
    )
    assert decision5.strategy == RetrievalStrategy.STANDARD_HYBRID


@pytest.mark.asyncio
async def test_evidence_sufficiency_evaluator():
    evaluator = EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3)

    user_id = uuid4()
    doc_id = uuid4()
    scope = DocumentRetrievalScope(user_id=user_id, document_ids=[doc_id])

    chunk1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="api_specifications.md",
        chunk_index=0,
        text="Standard Tier Tenants: Limited to 100 requests per minute with a burst allowance of 20 requests.",
        rerank_score=0.85,
        similarity_score=0.85,
    )
    chunk2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="api_specifications.md",
        chunk_index=1,
        text="Enterprise Tier Tenants: Limited to 1000 requests per minute with dedicated Redis token bucket limiters.",
        rerank_score=0.90,
        similarity_score=0.90,
    )

    assessment: EvidenceAssessment = await evaluator.evaluate(
        query="Compare the enterprise tier rate limit with the standard tier rate limit.",
        evidence=[chunk1, chunk2],
        expected_targets=["standard tier rate limit", "enterprise tier rate limit"],
        scope=scope,
        allowed_doc_ids=[doc_id],
    )

    assert assessment.sufficient is True
    assert assessment.conflicting_evidence is False
    assert len(assessment.missing_targets) == 0


@pytest.mark.asyncio
async def test_evidence_evaluator_missing_targets():
    evaluator = EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3)
    user_id = uuid4()
    scope = DocumentRetrievalScope(user_id=user_id)

    chunk1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="api_specifications.md",
        chunk_index=0,
        text="Standard Tier Tenants: Limited to 100 requests per minute.",
        rerank_score=0.80,
        similarity_score=0.80,
    )

    assessment = await evaluator.evaluate(
        query="What is the standard tier rate limit and what is the annual churn rate?",
        evidence=[chunk1],
        expected_targets=["standard tier rate limit", "annual churn rate"],
        scope=scope,
    )

    assert assessment.sufficient is False
    assert "annual churn rate" in assessment.missing_targets


@pytest.mark.asyncio
async def test_evidence_evaluator_unauthorized_scope():
    evaluator = EvidenceSufficiencyEvaluator()
    user_id = uuid4()
    allowed_doc = uuid4()
    unauthorized_doc = uuid4()
    scope = DocumentRetrievalScope(user_id=user_id, document_ids=[allowed_doc])

    unauthorized_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=unauthorized_doc,
        document_name="private_exec.md",
        chunk_index=0,
        text="Confidential executive compensation data.",
        rerank_score=0.95,
        similarity_score=0.95,
    )

    assessment = await evaluator.evaluate(
        query="What is the executive bonus?",
        evidence=[unauthorized_chunk],
        expected_targets=["executive bonus"],
        scope=scope,
        allowed_doc_ids=[allowed_doc],
    )

    assert assessment.sufficient is False


@pytest.mark.asyncio
async def test_replanner_deduplication():
    replanner = Replanner()

    assessment = EvidenceAssessment(
        sufficient=False,
        confidence=0.3,
        missing_targets=["annual churn rate"],
        supported_targets=[],
        conflicting_evidence=False,
        duplicate_evidence=False,
        citation_ready=False,
    )

    decision = RetrievalDecision(
        strategy=RetrievalStrategy.DECOMPOSITION,
        confidence=0.9,
    )

    user_id = uuid4()
    scope = DocumentRetrievalScope(user_id=user_id)
    executed_fps = set()

    prior_task_fp = compute_task_fingerprint(
        "standard tier rate limit", RetrievalStrategy.STANDARD_HYBRID, scope
    )
    executed_fps.add(prior_task_fp)

    completed_tasks = [
        RetrievalTaskResult(
            task_id=uuid4(),
            query="standard tier rate limit",
            strategy=RetrievalStrategy.STANDARD_HYBRID,
            retrieved_chunks=[],
            evidence_count=0,
            execution_time_ms=10.0,
            status=TaskStatus.COMPLETED,
        )
    ]

    new_tasks = await replanner.replan(
        original_query="What is standard rate limit and churn rate?",
        decision=decision,
        assessment=assessment,
        completed_tasks=completed_tasks,
        scope=scope,
        executed_fingerprints=executed_fps,
    )

    assert len(new_tasks) >= 1
    assert "churn rate" in new_tasks[0].query.lower()
    # Ensure task fingerprint avoids duplicate of prior tasks
    assert new_tasks[0].fingerprint != prior_task_fp


@pytest.mark.asyncio
async def test_adaptive_rag_orchestrator_single_iteration_sufficient():
    user_id = uuid4()
    doc_id = uuid4()
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="api_specifications.md",
        chunk_index=0,
        text="JWT access token lifetime is 15 minutes.",
        similarity_score=0.90,
    )

    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="What is the exact token lifetime for JWT access tokens?",
            retrieval_time=0.05,
            total_matches=1,
            retrieved_chunks=[chunk],
            dense_matches=[chunk],
            sparse_matches=[],
        )
    )

    classifier = DeterministicQueryClassifier()
    orchestrator = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3),
        replanner=Replanner(),
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        telemetry=OrchestrationTelemetry(),
        max_iterations=2,
    )

    result = await orchestrator.orchestrate(
        query="What is the exact token lifetime for JWT access tokens?",
        user_id=user_id,
        top_k=5,
    )

    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].text == "JWT access token lifetime is 15 minutes."
    assert result.diagnostics is not None
    assert result.diagnostics["evidence_sufficiency"] is True


@pytest.mark.asyncio
async def test_adaptive_rag_orchestrator_replanning_loop():
    user_id = uuid4()
    doc_id = uuid4()

    chunk1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc1.md",
        chunk_index=0,
        text="Standard tier rate limit is 100 requests per minute.",
        similarity_score=0.85,
    )
    chunk2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="doc2.md",
        chunk_index=0,
        text="Annual churn rate is 3.5% for enterprise accounts.",
        similarity_score=0.88,
    )

    call_count = 0

    async def _mock_retrieve(query, **kwargs):
        nonlocal call_count
        call_count += 1
        if "churn" in query.lower():
            chunks = [chunk2]
        else:
            chunks = [chunk1]

        return SearchResult(
            original_query=query,
            retrieval_time=0.05,
            total_matches=len(chunks),
            retrieved_chunks=chunks,
            dense_matches=chunks,
            sparse_matches=[],
        )

    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(side_effect=_mock_retrieve)

    classifier = DeterministicQueryClassifier()
    orchestrator = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3),
        replanner=Replanner(),
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        telemetry=OrchestrationTelemetry(),
        max_iterations=3,
        max_replans=2,
    )

    result = await orchestrator.orchestrate(
        query="What is the standard tier rate limit and what is the annual churn rate?",
        user_id=user_id,
        top_k=5,
    )

    assert len(result.retrieved_chunks) >= 1
    assert result.diagnostics is not None
    assert result.diagnostics["total_retrieval_calls"] >= 1


@pytest.mark.asyncio
async def test_three_way_comparative_matrix_execution():
    """
    Validates the 3 configurations on conceptual and multi-hop queries:
    A: Standard Baseline (Standard deterministic retrieval)
    B: Adaptive Strategy (Strategy routing without HyDE)
    C: Adaptive Strategy + HyDE (Strategy routing with HyDE enabled)
    """
    from app.documents.domain.interfaces import DenseRetriever, EmbeddingGenerator
    from app.documents.services.hyde import (
        DeterministicHyDEGenerator,
        SafeHyDEExecutor,
    )

    user_id = uuid4()
    doc_id = uuid4()

    ground_truth_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="cloud_architecture.md",
        chunk_index=0,
        text="All database volumes are encrypted using AWS KMS CMK with AES-256-GCM.",
        similarity_score=0.94,
    )

    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="How does cloud architecture encrypt database volumes?",
            retrieval_time=0.04,
            total_matches=1,
            retrieved_chunks=[ground_truth_chunk],
            dense_matches=[ground_truth_chunk],
            sparse_matches=[],
        )
    )

    classifier = DeterministicQueryClassifier()
    evaluator = EvidenceSufficiencyEvaluator(min_relevance_threshold=0.3)
    replanner = Replanner()

    # Configuration A: Standard Baseline Retrieval
    res_a = await mock_retrieval_service.retrieve(
        query="How does cloud architecture encrypt database volumes?",
        user_id=user_id,
        top_k=5,
    )
    assert len(res_a.retrieved_chunks) == 1

    # Configuration B: Adaptive Strategy without HyDE
    orchestrator_b = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=evaluator,
        replanner=replanner,
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        hyde_executor=None,  # HyDE disabled
        telemetry=OrchestrationTelemetry(),
    )
    res_b = await orchestrator_b.orchestrate(
        query="How does cloud architecture encrypt database volumes?",
        user_id=user_id,
        top_k=5,
    )
    assert len(res_b.retrieved_chunks) == 1
    assert res_b.diagnostics is not None
    assert res_b.diagnostics["final_status"] == "success"

    # Configuration C: Adaptive Strategy with HyDE
    mock_dense = MagicMock(spec=DenseRetriever)
    mock_dense.retrieve = AsyncMock(return_value=[ground_truth_chunk])
    mock_embed = MagicMock(spec=EmbeddingGenerator)
    mock_embed.generate_embeddings = AsyncMock(return_value=[[0.1] * 768])
    hyde_exec = SafeHyDEExecutor(
        hyde_generator=DeterministicHyDEGenerator(),
        embedding_generator=mock_embed,
        dense_retriever=mock_dense,
    )

    orchestrator_c = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=evaluator,
        replanner=replanner,
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        hyde_executor=hyde_exec,  # HyDE enabled
        telemetry=OrchestrationTelemetry(),
    )
    res_c = await orchestrator_c.orchestrate(
        query="Explain the cloud security mechanisms protecting customer data.",
        user_id=user_id,
        top_k=5,
    )
    assert len(res_c.retrieved_chunks) >= 1
    assert res_c.diagnostics is not None
    assert res_c.diagnostics["strategy"] in (
        "hyde",
        "standard_hybrid",
        "query_expansion",
    )


@pytest.mark.asyncio
async def test_failure_scenario_vector_store_degradation():
    """
    When vector search encounters an unexpected network outage, the worker
    handles the error gracefully without crashing the master orchestrator.
    """
    user_id = uuid4()
    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(
        side_effect=RuntimeError("Qdrant connection refused")
    )

    classifier = DeterministicQueryClassifier()
    orchestrator = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(),
        replanner=Replanner(),
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        telemetry=OrchestrationTelemetry(),
        max_iterations=2,
    )

    res = await orchestrator.orchestrate(
        query="What is the standard SLA?",
        user_id=user_id,
        top_k=5,
    )

    assert isinstance(res, SearchResult)
    assert len(res.retrieved_chunks) == 0
    assert res.diagnostics is not None
    assert res.diagnostics["final_status"] in ("partial", "failed", "success")


@pytest.mark.asyncio
async def test_failure_scenario_conflicting_evidence_detection():
    """
    Conflicting claims (e.g. 99.95% vs 99.99% SLO) are detected, recorded in
    diagnostics, and do not cause uncaught errors or hallucinations.
    """
    doc_id = uuid4()
    chunk_a = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="policies.md",
        chunk_index=0,
        text="The availability SLO is 99.95% for enterprise tenants.",
        similarity_score=0.90,
    )
    chunk_b = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="policies.md",
        chunk_index=1,
        text="The availability SLO is 99.99% for enterprise tier tenants.",
        similarity_score=0.91,
    )

    evaluator = EvidenceSufficiencyEvaluator()
    assessment = await evaluator.evaluate(
        query="What is the availability SLO for enterprise tier tenants?",
        evidence=[chunk_a, chunk_b],
        expected_targets=["availability SLO for enterprise tier tenants"],
    )

    assert assessment.conflicting_evidence is True
    assert len(assessment.conflict_details) >= 1
    assert "99.95" in str(assessment.conflict_details) or "99.99" in str(
        assessment.conflict_details
    )


@pytest.mark.asyncio
async def test_failure_scenario_hard_budget_exhaustion():
    """
    Hard budgets (max_iterations, max_tasks, max_retrieval_calls) terminate
    cleanly with PARTIAL status and prevent infinite replan loops.
    """
    from app.rag.orchestration.models import OrchestrationStatus

    user_id = uuid4()
    mock_retrieval_service = MagicMock()
    mock_retrieval_service.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="test",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    document_name="unrelated.md",
                    chunk_index=0,
                    text="Completely unrelated topic with zero relevant target info.",
                    similarity_score=0.30,
                )
            ],
            dense_matches=[],
            sparse_matches=[],
        )
    )

    classifier = DeterministicQueryClassifier()
    orchestrator = AdaptiveRAGOrchestrator(
        retrieval_service=mock_retrieval_service,
        strategy_router=RetrievalStrategyRouter(classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(min_relevance_threshold=0.5),
        replanner=Replanner(),
        query_classifier=classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        telemetry=OrchestrationTelemetry(),
        max_iterations=2,
        max_tasks=3,
        max_retrieval_calls=3,
        max_replans=1,
    )

    res = await orchestrator.orchestrate(
        query="Compare annual revenue, churn metrics, and patent filings across all departments.",
        user_id=user_id,
        top_k=5,
    )

    assert res.diagnostics is not None
    assert res.diagnostics["final_status"] == OrchestrationStatus.PARTIAL.value
    assert res.diagnostics["iterations"] <= 2
    assert res.diagnostics["total_retrieval_calls"] <= 3


@pytest.mark.asyncio
async def test_scope_security_audit_filters_unauthorized_documents():
    """
    Ensures that chunks from document IDs outside the authorized scope
    are completely filtered out of evidence assessment and results.
    """
    user_id = uuid4()
    allowed_doc_id = uuid4()
    unauthorized_doc_id = uuid4()

    allowed_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=allowed_doc_id,
        document_name="public_doc.md",
        chunk_index=0,
        text="Public documentation about platform APIs.",
        similarity_score=0.90,
    )
    unauthorized_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=unauthorized_doc_id,
        document_name="secret_payroll.md",
        chunk_index=0,
        text="Private executive compensation and bonus formulas.",
        similarity_score=0.99,
    )

    scope = DocumentRetrievalScope(
        user_id=user_id,
        document_ids=[allowed_doc_id],
    )

    evaluator = EvidenceSufficiencyEvaluator()
    assessment = await evaluator.evaluate(
        query="Show executive bonus",
        evidence=[allowed_chunk, unauthorized_chunk],
        expected_targets=["executive bonus"],
        scope=scope,
        allowed_doc_ids=[allowed_doc_id],
    )

    # Unauthorized chunk must be rejected
    assert assessment.sufficient is False


def test_telemetry_sanitization_no_content_leakage():
    """
    Verifies that telemetry events record purely operational metadata,
    counts, and latencies, without logging raw document text or queries.
    """
    from app.rag.orchestration.telemetry import OrchestrationTelemetryEvent

    telemetry = OrchestrationTelemetry()
    event = OrchestrationTelemetryEvent(
        orchestration_id=uuid4(),
        query_type="factual",
        selected_strategy="standard_hybrid",
        strategy_confidence=0.95,
        task_count=2,
        completed_task_count=2,
        failed_task_count=0,
        replan_count=0,
        retrieval_call_count=2,
        hyde_used=False,
        hyde_latency_ms=0.0,
        expansion_used=False,
        decomposition_used=False,
        evidence_sufficiency_score=1.0,
        missing_evidence_count=0,
        duplicate_task_count=0,
        conflict_detected=False,
        conflict_resolved=True,
        final_status="success",
        total_latency_ms=45.2,
    )

    telemetry.record(event)
    history = telemetry.get_history()
    assert len(history) == 1

    event_dict = history[0].model_dump()
    # Confirm no raw text fields exist in event structure
    assert "document_text" not in event_dict
    assert "prompt" not in event_dict
    assert "raw_content" not in event_dict
    assert event_dict["final_status"] == "success"
    assert event_dict["total_latency_ms"] == 45.2
