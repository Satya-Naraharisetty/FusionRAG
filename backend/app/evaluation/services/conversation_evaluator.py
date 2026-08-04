import logging

from app.evaluation.domain.models import (
    ConversationEvaluation,
    EvaluationResult,
    EvaluationSample,
)
from app.evaluation.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


class ConversationEvaluator:
    """
    Conversation Evaluator that leverages MetricRegistry to evaluate history rewrites,
    memory retention, summary quality, and context budgeting.
    """

    async def evaluate_samples(
        self,
        samples: list[EvaluationSample],
        mock: bool = False
    ) -> list[EvaluationResult]:
        results = []

        for sample in samples:
            rewritten_query = sample.metadata.get("rewritten_query") or ""
            actual_answer = sample.metadata.get("actual_answer") or ""
            memory_retention_score = sample.metadata.get("memory_retention_score") or 1.0
            summary_quality = sample.metadata.get("summary_quality") or 1.0
            tokens_used = sample.metadata.get("context_tokens_used") or 0
            error_category = sample.metadata.get("error_category") or "None"

            metric_results = []

            # 1. Run conversation metrics from registry
            m_rewrite = MetricRegistry.get_metric("history_rewriting").evaluate(sample, rewritten_query)
            m_budget = MetricRegistry.get_metric("context_budget_utilization").evaluate(sample, tokens_used)

            metric_results.extend([m_rewrite, m_budget])

            if not m_rewrite.passed:
                error_category = "Memory Failure"
            elif not m_budget.passed:
                error_category = "Context Overflow"

            conv_details = ConversationEvaluation(
                history_rewrite_score=m_rewrite.score,
                memory_retention_score=memory_retention_score,
                summary_quality_score=summary_quality,
                context_budget_utilization=m_budget.score,
                passed=m_rewrite.passed and m_budget.passed
            )

            sample_metadata = dict(sample.metadata)
            sample_metadata["conversation_evaluation"] = conv_details.model_dump()
            sample_metadata["error_category"] = error_category

            results.append(EvaluationResult(
                sample_id=sample.id,
                question=sample.question,
                expected_answer=sample.expected_answer,
                actual_answer=actual_answer,
                latency=sample.metadata.get("latency", 0.0),
                error_category=error_category,
                metrics=metric_results,
                retrieved_contexts=[],
                metadata=sample_metadata
            ))

        return results
