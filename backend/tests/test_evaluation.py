import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.domain.models import (
    EvaluationDataset,
    EvaluationSample,
    RelevantChunk,
    RetrievedContext,
)
from app.evaluation.metrics.registry import MetricRegistry
from app.evaluation.reports.report_generator import ReportGenerator
from app.evaluation.runners.benchmark_runner import BenchmarkRunner
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.runners.evaluation_runner import EvaluationRunner
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.runners.regression_runner import RegressionRunner
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.citation_evaluator import CitationEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator

# Absolute paths
_SIMPLE_DATASET_PATH = str(
    Path(__file__).parent / "evaluation" / "simple_rag_dataset.json"
)
_GOLDEN_DATASET_PATH = str(
    Path(__file__).parent.parent
    / "app"
    / "evaluation"
    / "datasets"
    / "golden"
    / "golden_v1.yaml"
)
_GOLDEN_DOCS_DIR = (
    Path(__file__).parent.parent
    / "app"
    / "evaluation"
    / "datasets"
    / "golden"
    / "documents"
)
_BASELINE_V1_PATH = str(
    Path(__file__).parent.parent
    / "app"
    / "evaluation"
    / "baselines"
    / "baseline_v1.json"
)


@pytest.fixture
def db_session():
    """
    Creates an in-memory SQLite database session specifically for testing
    evaluation persistence models.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


# ==============================================================================
# 1. Golden Dataset Integrity & Document Fixtures Tests
# ==============================================================================


def test_golden_dataset_integrity():
    """
    Verifies that the golden evaluation dataset:
    - Loads cleanly with DatasetLoader
    - Contains at least 50 samples (52 actual)
    - Represents all 12 target evaluation categories
    - Contains valid question strings and non-empty IDs
    - All referenced fixture documents exist on disk
    """
    loader = DatasetLoader()
    dataset = loader.load_dataset(_GOLDEN_DATASET_PATH, "golden_rag_dataset", "1.0.0")

    assert dataset.dataset_id == "golden_rag_dataset"
    assert dataset.version == "1.0.0"
    assert dataset.sample_count >= 50
    assert len(dataset.samples) == 52

    expected_categories = {
        "direct_factual",
        "multi_hop",
        "multi_document",
        "comparison",
        "explanation",
        "numerical_calculation",
        "citation_source",
        "conversation_context",
        "scope_restricted",
        "dense_vs_sparse",
        "reranker_improvement",
        "negative_control",
    }

    found_categories = {s.category for s in dataset.samples}
    assert expected_categories == found_categories, (
        f"Missing categories: {expected_categories - found_categories}"
    )

    # Verify fixture files exist on disk
    expected_fixture_files = {
        "cloud_architecture.md",
        "financial_report_2025.md",
        "engineering_policies.md",
        "api_specifications.md",
    }
    for filename in expected_fixture_files:
        doc_path = _GOLDEN_DOCS_DIR / filename
        assert doc_path.exists(), (
            f"Fixture document {filename} does not exist at {doc_path}"
        )
        assert doc_path.stat().st_size > 500, (
            f"Fixture document {filename} is suspiciously small."
        )

    # Verify each sample structure
    for s in dataset.samples:
        assert s.id.startswith("golden-")
        assert len(s.question.strip()) > 5
        if s.category == "negative_control":
            assert s.metadata.get("is_negative_control") is True
            assert len(s.expected_documents) == 0
        else:
            assert len(s.expected_documents) > 0
            assert len(s.relevant_chunks) > 0
            for rc in s.relevant_chunks:
                assert rc.document in expected_fixture_files
                assert rc.relevance in [1, 2, 3]


def test_dataset_loader_rejections():
    """
    Tests that DatasetLoader strictly rejects empty datasets and duplicate IDs.
    """
    loader = DatasetLoader()

    # Reject duplicate sample IDs
    sample1 = EvaluationSample(
        id="duplicate-id",
        question="What is X?",
        expected_answer="Y",
        expected_documents=["doc1.md"],
    )
    sample2 = EvaluationSample(
        id="duplicate-id",
        question="What is Z?",
        expected_answer="W",
        expected_documents=["doc2.md"],
    )
    dup_dataset = EvaluationDataset(
        dataset_id="test-dup",
        version="1.0.0",
        hash="hash123",
        sample_count=2,
        samples=[sample1, sample2],
    )
    with pytest.raises(ValueError, match="Duplicate sample ID"):
        loader.validate_dataset(dup_dataset, strict=True)

    # Reject empty dataset
    empty_dataset = EvaluationDataset(
        dataset_id="test-empty",
        version="1.0.0",
        hash="hash456",
        sample_count=0,
        samples=[],
    )
    with pytest.raises(ValueError, match="cannot be empty"):
        loader.validate_dataset(empty_dataset, strict=True)


# ==============================================================================
# 2. Retrieval Metrics Exact Calculations & Negative Control Tests
# ==============================================================================


def test_retrieval_metrics_exact_math():
    """
    Verifies exact calculations for hit_rate, precision@k, recall@k, mrr, and graded ndcg.
    """
    sample = EvaluationSample(
        id="test-eval-1",
        question="What is the encryption standard?",
        expected_documents=["cloud_architecture.md"],
        relevant_chunks=[
            RelevantChunk(
                document="cloud_architecture.md", section="Section 3", relevance=3
            ),
            RelevantChunk(
                document="cloud_architecture.md", section="Section 4", relevance=1
            ),
        ],
    )

    # Case 1: First retrieved item is rank 1 (highly relevant), second is rank 2 (moderately relevant), third is irrelevant
    contexts = [
        RetrievedContext(
            text="cloud_architecture.md Section 3 AES-256-GCM encryption", score=0.95
        ),
        RetrievedContext(
            text="cloud_architecture.md Section 4 Replication", score=0.80
        ),
        RetrievedContext(text="unrelated_doc.md Section 1 Overview", score=0.40),
    ]

    hit_rate = MetricRegistry.get_metric("hit_rate").evaluate(sample, contexts)
    assert hit_rate.score == 1.0

    prec = MetricRegistry.get_metric("precision_at_k").evaluate(sample, contexts)
    assert round(prec.score, 3) == round(2 / 3, 3)

    rec = MetricRegistry.get_metric("recall_at_k").evaluate(sample, contexts)
    assert rec.score == 1.0

    mrr = MetricRegistry.get_metric("mrr").evaluate(sample, contexts)
    assert mrr.score == 1.0  # First rank match -> 1/1 = 1.0

    ndcg = MetricRegistry.get_metric("ndcg").evaluate(sample, contexts)
    assert ndcg.score == 1.0  # Perfect ranking order -> 1.0


def test_retrieval_negative_control_metrics():
    """
    Verifies that negative control samples (zero expected chunks) do not cause division by zero
    or distort recall denominators.
    """
    neg_sample = EvaluationSample(
        id="test-neg-1",
        question="What is the policy on flying commercial first class?",
        expected_documents=[],
        relevant_chunks=[],
        metadata={"is_negative_control": True},
    )

    # If nothing was retrieved (ideal negative control response)
    empty_contexts: list[RetrievedContext] = []
    rec = MetricRegistry.get_metric("recall_at_k").evaluate(neg_sample, empty_contexts)
    assert rec.score == 1.0  # Expected 0 retrieved, received 0 retrieved

    hit = MetricRegistry.get_metric("hit_rate").evaluate(neg_sample, empty_contexts)
    assert hit.score == 1.0

    prec = MetricRegistry.get_metric("precision_at_k").evaluate(
        neg_sample, empty_contexts
    )
    assert prec.score == 1.0

    # If something was retrieved for a negative control (false positive)
    fp_contexts = [
        RetrievedContext(text="cloud_architecture.md some context", score=0.9)
    ]
    prec_fp = MetricRegistry.get_metric("precision_at_k").evaluate(
        neg_sample, fp_contexts
    )
    assert prec_fp.score == 0.0


# ==============================================================================
# 3. Citation Evaluator (Validity, Precision, Grounding, Coverage) Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_citation_evaluator_validity_precision_grounding():
    """
    Tests citation evaluation metrics:
    - citation_validity
    - citation_precision
    - citation_grounding
    - citation_coverage
    """
    evaluator = CitationEvaluator()

    sample = EvaluationSample(
        id="cite-sample-1",
        question="What is the token lifespan?",
        expected_answer="Access token lasts 15 minutes and refresh token lasts 7 days.",
        expected_documents=["api_specifications.md"],
        expected_citations=["api_specifications.md"],
        ground_truth_context=[
            "JWT access token lifetime is 15 minutes and refresh token is 7 days."
        ],
        metadata={
            "retrieved_contexts": [
                "api_specifications.md Section 1: JWT access token lifetime: 15m, refresh token: 7d"
            ],
            "citations": [
                {
                    "source_id": "api_specifications.md",
                    "text": "JWT access token lifetime: 15m, refresh token: 7d",
                    "claim": "Access token lasts 15 minutes",
                }
            ],
            "actual_answer": "Access token lasts 15 minutes [api_specifications.md].",
            "unauthorized_scope_citations": [],
        },
    )

    results = await evaluator.evaluate_samples([sample])
    assert len(results) == 1
    metrics = {m.name: m.score for m in results[0].metrics}

    assert metrics["citation_validity"] == 1.0
    assert metrics["citation_precision"] == 1.0
    assert metrics["citation_grounding"] == 1.0
    assert metrics["citation_coverage"] > 0.0


@pytest.mark.asyncio
async def test_citation_evaluator_unauthorized_scope_and_hallucination():
    """
    Tests citation evaluator behavior when citations point to unauthorized tenant documents
    or hallucinated non-existent chunk IDs.
    """
    evaluator = CitationEvaluator()

    sample = EvaluationSample(
        id="cite-sample-unauth",
        question="What is the secret key?",
        expected_documents=["public_spec.md"],
        metadata={
            "retrieved_contexts": ["public_spec.md content"],
            # Citation references another tenant's confidential document
            "citations": [
                {
                    "source_id": "tenant_999_confidential.md",
                    "text": "confidential tenant data",
                    "claim": "secret key is 12345",
                }
            ],
            "actual_answer": "The secret key is 12345 [tenant_999_confidential.md]",
            "unauthorized_scope_citations": ["tenant_999_confidential.md"],
        },
    )

    results = await evaluator.evaluate_samples([sample])
    assert len(results) == 1
    metrics = {m.name: m.score for m in results[0].metrics}

    # Citation validity must be 0 because source was unauthorized / not in authorized retrieved context
    assert metrics["citation_validity"] == 0.0
    assert metrics["citation_precision"] == 0.0


# ==============================================================================
# 4. Cross-Encoder Reranker Tradeoff Evaluation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_reranker_tradeoff_evaluation():
    """
    Tests evaluate_reranker_tradeoff calculating MRR, nDCG, Precision deltas and latency distribution.
    """
    from unittest.mock import MagicMock

    mock_retrieval_service = MagicMock()
    evaluator = RetrievalEvaluator(mock_retrieval_service)

    sample = EvaluationSample(
        id="rerank-sample-1",
        question="What is the IRSA token lifetime?",
        expected_documents=["cloud_architecture.md"],
        relevant_chunks=[
            RelevantChunk(
                document="cloud_architecture.md", section="Section 2", relevance=3
            )
        ],
        metadata={"benefit_from_reranking": True},
    )

    tradeoff = await evaluator.evaluate_reranker_tradeoff([sample], mock=True)

    assert "without_reranker_mrr" in tradeoff
    assert "with_reranker_mrr" in tradeoff
    assert "mrr_delta" in tradeoff
    assert "without_reranker_ndcg" in tradeoff
    assert "with_reranker_ndcg" in tradeoff
    assert "ndcg_delta" in tradeoff
    assert "reranker_latency_avg_ms" in tradeoff
    assert "reranker_latency_p50_ms" in tradeoff
    assert "reranker_latency_p95_ms" in tradeoff
    assert tradeoff["mrr_delta"] >= 0.0


# ==============================================================================
# 5. Observable Multi-Agent Metrics Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_multi_agent_observable_metrics():
    """
    Verifies that AgentEvaluator properly computes task success rate, evidence sufficiency,
    replan success rate, duplicate task avoidance, and call efficiency from execution metadata.
    """
    agent_eval = AgentEvaluator()

    sample = EvaluationSample(
        id="agent-sample-1",
        question="Compute combined EMEA and APAC revenue.",
        expected_documents=["financial_report_2025.md"],
        metadata={
            "reasoning_steps": 2,
            "actual_tools": ["calculator"],
            "planned_tasks": ["retrieve_emea", "retrieve_apac", "sum_totals"],
            "completed_tasks": ["retrieve_emea", "retrieve_apac", "sum_totals"],
            "failed_tasks": [],
            "research_tasks_total": 2,
            "research_tasks_sufficient": 2,
            "replan_attempts": 0,
            "replan_successes": 0,
            "duplicate_task_count": 0,
            "total_agent_calls": 3,
            "productive_agent_calls": 3,
        },
    )

    results = await agent_eval.evaluate_samples([sample])
    assert len(results) == 1
    metrics = {m.name: m.score for m in results[0].metrics}

    assert metrics["task_success_rate"] == 1.0
    assert metrics["evidence_sufficiency_rate"] == 1.0
    assert metrics["duplicate_task_avoidance"] == 1.0
    assert metrics["agent_call_efficiency"] == 1.0


# ==============================================================================
# 6. Baseline Data Loading & Compatibility Verification Tests
# ==============================================================================


def test_baseline_data_loading_and_compatibility():
    """
    Verifies loading the true baseline_v1.json and validating version compatibility.
    """
    runner = RegressionRunner()

    assert os.path.exists(_BASELINE_V1_PATH), (
        "baseline_v1.json artifact file not found!"
    )
    baseline = runner.load_baseline_file(_BASELINE_V1_PATH)

    assert baseline.baseline_version == "v1"
    assert baseline.dataset_version == "1.0.0"
    assert baseline.evaluator_version == "v1"
    assert baseline.profile == "fast_deterministic"
    assert baseline.sample_count == 52
    assert "mrr" in baseline.metric_averages
    assert "ndcg" in baseline.metric_averages
    assert "hit_rate" in baseline.metric_averages

    # Mismatched dataset version must raise ValueError
    with pytest.raises(ValueError, match="dataset version mismatch"):
        runner.compare_with_baseline_data(
            candidate_metrics={"mrr": 0.95},
            candidate_latency=0.001,
            baseline=baseline,
            candidate_dataset_version="2.0.0",
            candidate_profile="fast_deterministic",
        )

    # Mismatched profile must raise ValueError
    with pytest.raises(ValueError, match="profile mismatch"):
        runner.compare_with_baseline_data(
            candidate_metrics={"mrr": 0.95},
            candidate_latency=0.001,
            baseline=baseline,
            candidate_dataset_version="1.0.0",
            candidate_profile="nightly",
        )


# ==============================================================================
# 7. Deliberate Quality Regression Detection Test
# ==============================================================================


def test_regression_runner_detects_deliberate_quality_regression():
    """
    Deliberately creates a candidate run with broken metrics (e.g. MRR dropped by 0.15),
    verifies that:
    1. regression_result.passed is False
    2. The exact metric is identified in regressions list
    3. The regression is properly classified
    """
    runner = RegressionRunner()
    baseline = runner.load_baseline_file(_BASELINE_V1_PATH)

    # Candidate with a severe MRR regression (e.g. 0.80 vs baseline 0.962 -> drop of 0.162 > 0.03 threshold)
    candidate_metrics = dict(baseline.metric_averages)
    candidate_metrics["mrr"] = 0.80

    regression_result = runner.compare_with_baseline_data(
        candidate_metrics=candidate_metrics,
        candidate_latency=baseline.latency_metrics["avg_latency"],
        baseline=baseline,
        candidate_dataset_version=baseline.dataset_version,
        candidate_profile=baseline.profile,
        max_score_drop=0.03,
    )

    assert regression_result.passed is False
    assert len(regression_result.details["regressions"]) >= 1

    reg_metrics = [r["metric"] for r in regression_result.details["regressions"]]
    assert "mrr" in reg_metrics

    mrr_reg = next(
        r for r in regression_result.details["regressions"] if r["metric"] == "mrr"
    )
    assert mrr_reg["candidate"] == 0.80
    assert mrr_reg["delta"] < -0.03
    assert mrr_reg["status"] == "REGRESSION"


# ==============================================================================
# 8. End-to-End Fast Deterministic Benchmark Execution Test
# ==============================================================================


@pytest.mark.asyncio
async def test_fast_deterministic_benchmark_execution(db_session):
    """
    Executes the fast_deterministic profile against golden_v1.yaml with in-memory DB,
    verifying run status, sample persistence, and non-empty quality reports.
    """
    retrieval_service_mock = MagicMock()
    retrieval_eval = RetrievalEvaluator(retrieval_service_mock)
    agent_eval = AgentEvaluator()
    tool_eval = ToolEvaluator()
    conv_eval = ConversationEvaluator()
    citation_eval = CitationEvaluator()

    ragas_prov = RagasProvider()
    deepeval_prov = DeepEvalProvider()

    eval_runner = EvaluationRunner(
        retrieval_evaluator=retrieval_eval,
        agent_evaluator=agent_eval,
        tool_evaluator=tool_eval,
        conversation_evaluator=conv_eval,
        citation_evaluator=citation_eval,
        ragas_provider=ragas_prov,
        deepeval_provider=deepeval_prov,
    )

    runner = BenchmarkRunner(evaluation_runner=eval_runner)
    loader = DatasetLoader()
    dataset = loader.load_dataset(_GOLDEN_DATASET_PATH, "golden_rag_dataset", "1.0.0")

    run_record = await runner.run_benchmark(
        db=db_session,
        dataset=dataset,
        profile="fast_deterministic",
        mock=True,
    )

    assert run_record.status == "COMPLETED"
    assert run_record.total_samples == 52
    assert run_record.completed_samples == 52

    report_gen = ReportGenerator()
    reports = report_gen.generate_all_reports(run_record)

    assert os.path.exists(reports["markdown"])
    assert os.path.exists(reports["json"])

    with open(reports["markdown"], encoding="utf-8") as f:
        md_text = f.read()
        assert "RAG Benchmark Report" in md_text
        assert "Cross-Encoder Reranker Impact & Latency Tradeoff" in md_text
