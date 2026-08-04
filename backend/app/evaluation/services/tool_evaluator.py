import logging

from app.evaluation.domain.models import (
    EvaluationResult,
    EvaluationSample,
    ToolEvaluation,
)
from app.evaluation.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


class ToolEvaluator:
    """
    Tool Evaluator that leverages MetricRegistry to evaluate execution success rate,
    retries, and tool choice correctness.
    """

    async def evaluate_samples(
        self,
        samples: list[EvaluationSample],
        mock: bool = False
    ) -> list[EvaluationResult]:
        results = []

        for sample in samples:
            failures = sample.metadata.get("tool_failures") or 0
            validation_errs = sample.metadata.get("tool_validation_failures") or 0
            timeouts = sample.metadata.get("tool_timeouts") or 0
            retries = sample.metadata.get("tool_retries") or 0
            total_tool_calls = sample.metadata.get("total_tool_calls") or 0
            latency = sample.metadata.get("tool_latency") or 0.0
            error_category = sample.metadata.get("error_category") or "None"
            actual_tools = sample.metadata.get("actual_tools") or []

            metric_results = []

            # 1. Run tool metrics from registry
            m_success = MetricRegistry.get_metric("tool_success_rate").evaluate(
                sample,
                {"total_tool_calls": total_tool_calls, "tool_failures": failures}
            )
            m_choice = MetricRegistry.get_metric("tool_choice_correctness").evaluate(sample, actual_tools)

            metric_results.extend([m_success, m_choice])

            if not m_choice.passed:
                error_category = "Wrong Tool"
            elif not m_success.passed:
                error_category = "Provider Error"
            if timeouts > 0:
                error_category = "Timeout"

            tool_details = ToolEvaluation(
                tool_success_rate=m_success.score,
                validation_failures=validation_errs,
                timeouts=timeouts,
                retries=retries,
                latency=latency,
                correct_tool_chosen=m_choice.passed,
                passed=m_success.passed and m_choice.passed and (timeouts == 0)
            )

            sample_metadata = dict(sample.metadata)
            sample_metadata["tool_evaluation"] = tool_details.model_dump()
            sample_metadata["error_category"] = error_category

            results.append(EvaluationResult(
                sample_id=sample.id,
                question=sample.question,
                expected_answer=sample.expected_answer,
                actual_answer=sample.metadata.get("actual_answer"),
                latency=sample.metadata.get("latency", 0.0),
                error_category=error_category,
                metrics=metric_results,
                retrieved_contexts=[],
                metadata=sample_metadata
            ))

        return results
