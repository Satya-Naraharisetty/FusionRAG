import logging

from app.evaluation.domain.models import (
    AgentEvaluation,
    EvaluationResult,
    EvaluationSample,
)
from app.evaluation.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


class AgentEvaluator:
    """
    Agent Evaluator that leverages MetricRegistry to evaluate reasoning steps,
    tool necessity, tool sequence, and execution efficiency.
    """

    async def evaluate_samples(
        self, samples: list[EvaluationSample], mock: bool = False
    ) -> list[EvaluationResult]:
        results = []

        for sample in samples:
            steps = sample.metadata.get("reasoning_steps") or 0
            actual_tools = sample.metadata.get("actual_tools") or []
            latency = sample.metadata.get("latency") or 0.0
            error_category = sample.metadata.get("error_category") or "None"

            metric_results = []

            # 1. Run reasoning metrics from registry
            m_steps = MetricRegistry.get_metric("reasoning_steps").evaluate(
                sample, steps
            )
            m_necessity = MetricRegistry.get_metric("tool_necessity").evaluate(
                sample, actual_tools
            )
            m_ordering = MetricRegistry.get_metric("tool_ordering").evaluate(
                sample, actual_tools
            )
            m_efficiency = MetricRegistry.get_metric("reasoning_efficiency").evaluate(
                sample, steps
            )

            metric_results.extend([m_steps, m_necessity, m_ordering, m_efficiency])

            if not m_steps.passed:
                error_category = "Context Overflow"
            elif not m_necessity.passed:
                error_category = "Wrong Tool"

            agent_details = AgentEvaluation(
                reasoning_steps=steps,
                reasoning_efficiency=m_efficiency.score,
                tool_necessity_score=m_necessity.score,
                tool_ordering_correctness=m_ordering.score,
                iteration_count=steps,
                passed=all(m.passed for m in metric_results if m.passed is not None),
            )

            sample_metadata = dict(sample.metadata)
            sample_metadata["agent_evaluation"] = agent_details.model_dump()
            sample_metadata["error_category"] = error_category

            results.append(
                EvaluationResult(
                    sample_id=sample.id,
                    question=sample.question,
                    expected_answer=sample.expected_answer,
                    actual_answer=sample.metadata.get("actual_answer"),
                    latency=latency,
                    error_category=error_category,
                    metrics=metric_results,
                    retrieved_contexts=[],
                    metadata=sample_metadata,
                )
            )

        return results
