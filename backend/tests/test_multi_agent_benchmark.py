import os

import pytest
import yaml

from app.evaluation.domain.models import EvaluationDataset, EvaluationSample
from app.evaluation.services.multi_agent_evaluator import MultiAgentEvaluator


@pytest.fixture
def evaluator() -> MultiAgentEvaluator:
    return MultiAgentEvaluator()


@pytest.fixture
def sample_dataset() -> EvaluationDataset:
    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app",
        "evaluation",
        "datasets",
        "golden",
        "golden_multi_agent.yaml",
    )
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    samples = [
        EvaluationSample(
            id=s["id"],
            question=s["question"],
            expected_answer=s.get("expected_answer"),
            retrieval_required=s.get("retrieval_required", True),
            metadata=s.get("metadata", {}),
        )
        for s in data["samples"]
    ]
    return EvaluationDataset(
        dataset_id=data["dataset_id"],
        version=data["version"],
        hash="test-hash",
        sample_count=len(samples),
        description=data.get("description"),
        samples=samples,
    )


@pytest.mark.asyncio
async def test_multi_agent_evaluator_evaluates_all_six_areas(
    evaluator: MultiAgentEvaluator, sample_dataset: EvaluationDataset
):
    """Verify that MultiAgentEvaluator evaluates planning, routing, dependencies, replanning, calculation, and grounding."""
    results = await evaluator.evaluate_samples(sample_dataset.samples)
    assert len(results) == len(sample_dataset.samples)

    for res in results:
        metric_names = {m.name for m in res.metrics}
        assert "multi_agent_planning_accuracy" in metric_names
        assert "multi_agent_routing_accuracy" in metric_names
        assert "multi_agent_dependency_execution" in metric_names
        assert "multi_agent_replanning_success" in metric_names
        assert "multi_agent_calculation_accuracy" in metric_names
        assert "multi_agent_synthesis_grounding" in metric_names

        # Verify all metrics passed on golden dataset
        for m in res.metrics:
            assert m.passed is True, (
                f"Metric {m.name} failed for sample {res.sample_id}: {m.reason}"
            )

        # Verify structured evaluation details
        eval_dict = res.metadata.get("multi_agent_evaluation", {})
        assert eval_dict.get("passed") is True
        assert eval_dict.get("planning_accuracy") >= 0.8


@pytest.mark.asyncio
async def test_planning_accuracy_detects_missing_specialist(
    evaluator: MultiAgentEvaluator,
):
    """Verify planning accuracy metric catches plans missing expected specialists."""
    sample = EvaluationSample(
        id="s_plan_fail",
        question="Research and analyze growth",
        metadata={
            "expected_specialists": ["RESEARCH", "ANALYSIS", "SYNTHESIS"],
            "actual_tasks": [
                {"task_id": "t1", "agent_type": "RESEARCH", "success": True}
            ],
            "agent_diagnostics": {"plan_iterations": 1},
        },
    )
    results = await evaluator.evaluate_samples([sample])
    res = results[0]
    m_plan = next(m for m in res.metrics if m.name == "multi_agent_planning_accuracy")
    assert m_plan.passed is False
    assert m_plan.score < 0.8


@pytest.mark.asyncio
async def test_calculation_accuracy_detects_numerical_errors(
    evaluator: MultiAgentEvaluator,
):
    """Verify calculation accuracy fails when actual output does not match expected output."""
    sample = EvaluationSample(
        id="s_calc_fail",
        question="Compute growth",
        metadata={
            "expected_numeric_output": 50.0,
            "actual_numeric_output": 40.0,
            "actual_tasks": [],
            "agent_diagnostics": {"plan_iterations": 1},
        },
    )
    results = await evaluator.evaluate_samples([sample])
    res = results[0]
    m_calc = next(
        m for m in res.metrics if m.name == "multi_agent_calculation_accuracy"
    )
    assert m_calc.passed is False
    assert m_calc.score == 0.0


@pytest.mark.asyncio
async def test_replanning_detection(evaluator: MultiAgentEvaluator):
    """Verify replanning evaluation confirms bounded replan iterations when expected."""
    sample_replan = EvaluationSample(
        id="s_replan",
        question="Incomplete query requiring refinement",
        metadata={
            "trigger_replan": True,
            "actual_tasks": [],
            "agent_diagnostics": {"plan_iterations": 2},
        },
    )
    results = await evaluator.evaluate_samples([sample_replan])
    res = results[0]
    m_replan = next(
        m for m in res.metrics if m.name == "multi_agent_replanning_success"
    )
    assert m_replan.passed is True
    assert m_replan.score == 1.0


@pytest.mark.asyncio
async def test_grounding_evaluates_citations(evaluator: MultiAgentEvaluator):
    """Verify grounding metric validates evidence-citation correspondence."""
    sample_ungrounded = EvaluationSample(
        id="s_ground_fail",
        question="Policy question",
        retrieval_required=True,
        metadata={
            "actual_tasks": [],
            "agent_diagnostics": {"evidence_count": 5, "plan_iterations": 1},
            "citations": [],  # Empty citations despite evidence retrieved
        },
    )
    results = await evaluator.evaluate_samples([sample_ungrounded])
    res = results[0]
    m_ground = next(
        m for m in res.metrics if m.name == "multi_agent_synthesis_grounding"
    )
    assert m_ground.score == 0.5
    assert m_ground.passed is False
