import os
import uuid
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.runners.benchmark_runner import BenchmarkRunner
from app.evaluation.runners.regression_runner import RegressionRunner
from app.evaluation.reports.report_generator import ReportGenerator
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun, SQLAlchemyEvaluationResult


@pytest.fixture
def db_session():
    """
    Creates an in-memory SQLite database session specifically for testing
    evaluation persistence models.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def test_dataset_loader():
    loader = DatasetLoader()
    dataset_path = "tests/evaluation/simple_rag_dataset.json"
    
    # Check loading
    dataset = loader.load_dataset(dataset_path, "test-ds", "1.0.0")
    assert dataset.dataset_id == "test-ds"
    assert dataset.version == "1.0.0"
    assert dataset.sample_count == 2
    assert len(dataset.samples) == 2
    assert dataset.samples[0].id == "rag-01"
    assert dataset.samples[0].difficulty == "easy"
    assert dataset.samples[1].difficulty == "medium"
    assert dataset.hash is not None

    # Check validation
    assert loader.validate_dataset(dataset) is True

    # Check sampling
    subset = loader.sampling(dataset, 1)
    assert subset.sample_count == 1
    assert len(subset.samples) == 1

    # Check filtering
    filtered = loader.filtering(dataset, difficulty="easy")
    assert filtered.sample_count == 1
    assert filtered.samples[0].id == "rag-01"


@pytest.mark.asyncio
async def test_ragas_and_deepeval_mock_providers():
    loader = DatasetLoader()
    dataset = loader.load_dataset("tests/evaluation/simple_rag_dataset.json", "test-ds", "1.0.0")

    ragas = RagasProvider()
    deepeval = DeepEvalProvider()

    # Ragas Mock run
    ragas_results = await ragas.evaluate(
        dataset.samples,
        metrics=["faithfulness", "answer_relevancy"],
        mock=True
    )
    assert len(ragas_results) == 2
    assert ragas_results[0].sample_id == "rag-01"
    assert len(ragas_results[0].metrics) == 2
    assert any(m.name == "faithfulness" for m in ragas_results[0].metrics)

    # DeepEval Mock run
    deepeval_results = await deepeval.evaluate(
        dataset.samples,
        metrics=["hallucination", "tool_correctness"],
        mock=True
    )
    assert len(deepeval_results) == 2
    assert deepeval_results[0].sample_id == "rag-01"
    assert any(m.name == "hallucination" for m in deepeval_results[0].metrics)


@pytest.mark.asyncio
async def test_retrieval_evaluator_math():
    # Instantiate retrieval evaluator with a mock service
    from unittest.mock import MagicMock
    retrieval_service_mock = MagicMock()
    
    evaluator = RetrievalEvaluator(retrieval_service_mock)
    
    loader = DatasetLoader()
    dataset = loader.load_dataset("tests/evaluation/simple_rag_dataset.json", "test-ds", "1.0.0")

    # Run in mock mode to verify calculations
    results = await evaluator.evaluate_samples(dataset.samples, mock=True)
    assert len(results) == 2
    assert results[0].error_category == "None"
    
    # Verify Recall and Precision are computed
    metrics_dict = {m.name: m.score for m in results[0].metrics}
    assert "precision_at_k" in metrics_dict
    assert "recall_at_k" in metrics_dict
    assert "hit_rate" in metrics_dict
    assert "mrr" in metrics_dict
    assert "ndcg" in metrics_dict


@pytest.mark.asyncio
async def test_agent_tool_conversation_evaluators():
    agent_eval = AgentEvaluator()
    tool_eval = ToolEvaluator()
    conv_eval = ConversationEvaluator()

    loader = DatasetLoader()
    dataset = loader.load_dataset("tests/evaluation/simple_rag_dataset.json", "test-ds", "1.0.0")

    # Add mock execution metadata
    for sample in dataset.samples:
        sample.metadata["reasoning_steps"] = 1
        sample.metadata["actual_tools"] = ["calculator"]
        sample.metadata["total_tool_calls"] = 1
        sample.metadata["tool_failures"] = 0
        sample.metadata["rewritten_query"] = "rewritten search question"
        sample.metadata["context_tokens_used"] = 400

    agent_res = await agent_eval.evaluate_samples(dataset.samples)
    assert len(agent_res) == 2
    assert any(m.name == "reasoning_steps" for m in agent_res[0].metrics)

    tool_res = await tool_eval.evaluate_samples(dataset.samples)
    assert len(tool_res) == 2
    assert any(m.name == "tool_success_rate" for m in tool_res[0].metrics)

    conv_res = await conv_eval.evaluate_samples(dataset.samples)
    assert len(conv_res) == 2
    assert any(m.name == "history_rewriting" for m in conv_res[0].metrics)


@pytest.mark.asyncio
async def test_benchmark_runner_and_regression_checks(db_session):
    from unittest.mock import MagicMock
    retrieval_service_mock = MagicMock()
    
    retrieval_eval = RetrievalEvaluator(retrieval_service_mock)
    agent_eval = AgentEvaluator()
    tool_eval = ToolEvaluator()
    conv_eval = ConversationEvaluator()
    
    ragas_prov = RagasProvider()
    deepeval_prov = DeepEvalProvider()

    from app.evaluation.runners.evaluation_runner import EvaluationRunner

    eval_runner = EvaluationRunner(
        retrieval_evaluator=retrieval_eval,
        agent_evaluator=agent_eval,
        tool_evaluator=tool_eval,
        conversation_evaluator=conv_eval,
        ragas_provider=ragas_prov,
        deepeval_provider=deepeval_prov
    )

    runner = BenchmarkRunner(evaluation_runner=eval_runner)

    loader = DatasetLoader()
    dataset = loader.load_dataset("tests/evaluation/simple_rag_dataset.json", "test-ds", "1.0.0")

    # Run Benchmark (Baseline Run)
    baseline_run = await runner.run_benchmark(
        db=db_session,
        dataset=dataset,
        profile="quick",
        mock=True
    )
    assert baseline_run.status == "COMPLETED"
    assert baseline_run.total_samples == 2
    assert len(db_session.query(SQLAlchemyEvaluationResult).all()) == 2

    # Run Benchmark again (Candidate Run)
    candidate_run = await runner.run_benchmark(
        db=db_session,
        dataset=dataset,
        profile="quick",
        mock=True
    )
    assert candidate_run.status == "COMPLETED"

    # Verify Regression comparison
    regression_runner = RegressionRunner()
    regression_result = regression_runner.compare_runs(
        db=db_session,
        candidate_run_id=candidate_run.id,
        baseline_run_id=baseline_run.id
    )
    
    assert regression_result.passed is True
    assert regression_result.baseline_run_id == baseline_run.id
    assert regression_result.candidate_run_id == candidate_run.id
    assert "recall_at_k" in regression_result.metric_deltas


def test_report_generation(db_session):
    # Setup mock run in DB
    run_record = SQLAlchemyEvaluationRun(
        id=uuid.uuid4(),
        name="Test Run For Reports",
        profile="quick",
        dataset_id="test-ds",
        dataset_version="1.0.0",
        provider="gemini",
        model="gemini-1.5-flash",
        temperature=0.0,
        embedding_model="text-embedding-3-small",
        reranker="identity",
        retrieval_mode="hybrid",
        system_prompt_version="1.0.0",
        git_commit="hash",
        git_branch="main",
        status="COMPLETED",
        total_samples=1,
        completed_samples=1,
        created_at=datetime.utcnow()
    )
    db_session.add(run_record)
    db_session.commit()

    result_record = SQLAlchemyEvaluationResult(
        id=uuid.uuid4(),
        run_id=run_record.id,
        sample_id="sample-1",
        question="What is this?",
        expected_answer="answer",
        actual_answer="actual",
        latency=0.1,
        input_tokens=100,
        output_tokens=50,
        cost=0.0001,
        error_category="None",
        metrics={"faithfulness": {"score": 0.95, "passed": True, "reason": "Good"}},
        retrieved_contexts=[],
        metadata_json={}
    )
    db_session.add(result_record)
    db_session.commit()

    # Generate Reports
    output_dir = "data/evaluation_test"
    report_gen = ReportGenerator(output_dir=output_dir)
    paths = report_gen.generate_all_reports(run_record)

    assert os.path.exists(paths["markdown"])
    assert os.path.exists(paths["json"])
    assert os.path.exists(paths["csv"])
    assert os.path.exists(paths["html"])

    # Clean up generated files
    for p in paths.values():
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(output_dir):
        os.rmdir(output_dir)


@pytest.mark.asyncio
async def test_api_routes(client):
    # The endpoints check authentication, which triggers get_current_user_context.
    # In tests, get_current_user_context returns mock context of a user.
    # Let's verify route access or validation check.
    # To test admin route, we mock the dependency override
    from app.main import app
    from app.api.v1.evaluation import check_admin_user

    # Mock admin override
    app.dependency_overrides[check_admin_user] = lambda: {"user_id": str(uuid.uuid4()), "role": "admin"}
    
    # Test listing runs (returns empty or list)
    response = client.get("/api/v1/evaluation/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Clean up override
    app.dependency_overrides.pop(check_admin_user, None)
