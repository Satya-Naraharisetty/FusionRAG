import logging
import math
from typing import Any

from app.core.config import settings
from app.evaluation.domain.models import (
    EvaluationSample,
    MetricResult,
    RetrievedContext,
)
from app.evaluation.metrics.base import Metric

logger = logging.getLogger(__name__)


class MetricRegistry:
    """
    Registry for evaluation metrics to decouple metric calculations from evaluators.
    """

    _registry: dict[str, type[Metric]] = {}

    @classmethod
    def register(cls, name: str) -> Any:
        """
        Decorator to register a Metric class.
        """
        def decorator(metric_cls: type[Metric]) -> type[Metric]:
            cls._registry[name] = metric_cls
            return metric_cls
        return decorator

    @classmethod
    def get_metric(cls, name: str, **kwargs: Any) -> Metric:
        if name not in cls._registry:
            raise KeyError(f"Metric '{name}' is not registered. Available: {list(cls._registry.keys())}")
        return cls._registry[name](name=name, **kwargs)

    @classmethod
    def list_metrics(cls) -> list[str]:
        return list(cls._registry.keys())


# Helper for word overlap calculation used across heuristic metrics
def compute_word_overlap(text1: str, text2: str) -> float:
    def get_words(t: str) -> set[str]:
        return {w.strip(".,!?;:()[]\"'").lower() for w in t.split() if len(w) > 2}

    w1 = get_words(text1)
    w2 = get_words(text2)
    if not w1 or not w2:
        return 0.0
    intersection = w1.intersection(w2)
    union = w1.union(w2)
    return len(intersection) / len(union)


# Helper to determine relevance of retrieved contexts
def calculate_relevance(retrieved: list[RetrievedContext], sample: EvaluationSample) -> list[float]:
    relevance = []
    expected_docs = sample.expected_documents or []
    gts = sample.ground_truth_context or []

    for c in retrieved:
        if c.document_id and c.document_id in expected_docs:
            relevance.append(1.0)
            continue
        if c.chunk_id and c.chunk_id in expected_docs:
            relevance.append(1.0)
            continue

        is_relevant = False
        for gt in gts:
            if len(gt) > 10 and (gt.lower() in c.text.lower() or c.text.lower() in gt.lower()):
                is_relevant = True
                break
            overlap = compute_word_overlap(c.text, gt)
            if overlap >= 0.4:
                is_relevant = True
                break

        relevance.append(1.0 if is_relevant else 0.0)

    return relevance


# --- REGISTRATION OF STANDARD METRICS ---

@MetricRegistry.register("hit_rate")
class HitRateMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        hit = 1.0 if any(relevance) else 0.0
        return MetricResult(
            name=self.name,
            score=hit,
            passed=hit > 0.0,
            reason=f"Hit found in top {len(retrieved_contexts)} retrieved chunks." if hit > 0 else "No ground truth context retrieved."
        )


@MetricRegistry.register("precision_at_k")
class PrecisionAtKMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        precision = sum(relevance) / len(relevance) if relevance else 0.0
        passed = precision >= settings.THRESHOLD_CONTEXT_PRECISION
        return MetricResult(
            name=self.name,
            score=round(precision, 3),
            passed=passed,
            reason=f"{sum(relevance)} out of {len(relevance)} retrieved chunks are relevant."
        )


@MetricRegistry.register("recall_at_k")
class RecallAtKMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        total_relevant = len(sample.ground_truth_context or []) or len(sample.expected_documents or []) or 1
        recall = sum(relevance) / total_relevant
        passed = recall >= settings.THRESHOLD_CONTEXT_RECALL
        return MetricResult(
            name=self.name,
            score=round(recall, 3),
            passed=passed,
            reason=f"Retrieved {sum(relevance)} out of {total_relevant} expected relevant items."
        )


@MetricRegistry.register("mrr")
class MRRMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        mrr = 0.0
        idx = 0
        for idx, rel in enumerate(relevance):
            if rel:
                mrr = 1.0 / (idx + 1)
                break
        return MetricResult(
            name=self.name,
            score=round(mrr, 3),
            passed=mrr >= 0.5,
            reason=f"First relevant item found at rank {idx + 1}." if mrr > 0 else "No relevant items found."
        )


@MetricRegistry.register("ndcg")
class NDCGMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        total_relevant = len(sample.ground_truth_context or []) or len(sample.expected_documents or []) or 1
        dcg = sum(1.0 / math.log2(idx + 2) for idx, rel in enumerate(relevance) if rel)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevance), total_relevant)))
        ndcg = dcg / idcg if idcg > 0 else 0.0
        return MetricResult(
            name=self.name,
            score=round(ndcg, 3),
            passed=ndcg >= 0.70,
            reason=f"Normalized Discounted Cumulative Gain: {ndcg:.3f}."
        )


@MetricRegistry.register("reasoning_steps")
class ReasoningStepsMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        steps = int(actual_output) if actual_output is not None else 0
        passed = True
        if sample.tools_required and steps == 0:
            passed = False
        elif steps > settings.MAX_TOOL_ITERATIONS:
            passed = False
        return MetricResult(
            name=self.name,
            score=float(steps),
            passed=passed,
            reason=f"Executed {steps} reasoning steps. Limit: {settings.MAX_TOOL_ITERATIONS}."
        )


@MetricRegistry.register("tool_necessity")
class ToolNecessityMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        actual_tools = actual_output if isinstance(actual_output, list) else []
        score = 1.0
        if not sample.tools_required and len(actual_tools) > 0:
            score = 0.0
            passed = False
            reason = "Tools were called but none were required."
        else:
            passed = True
            reason = "Tool necessity is correct."
        return MetricResult(
            name=self.name,
            score=score,
            passed=passed,
            reason=reason
        )


@MetricRegistry.register("tool_ordering")
class ToolOrderingMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        actual_tools = actual_output if isinstance(actual_output, list) else []
        expected_tools = sample.expected_tools or []
        score = 1.0
        if expected_tools and actual_tools:
            matches = sum(1 for idx, tool in enumerate(actual_tools) if idx < len(expected_tools) and tool == expected_tools[idx])
            score = matches / max(len(expected_tools), len(actual_tools))
        elif expected_tools and not actual_tools:
            score = 0.0
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.70,
            reason=f"Tool calling order similarity: {score * 100:.1f}%."
        )


@MetricRegistry.register("reasoning_efficiency")
class ReasoningEfficiencyMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        steps = int(actual_output) if actual_output is not None else 0
        efficiency = 1.0
        if steps > 0:
            efficiency = 1.0 / (steps * 0.5 + 0.5)
        return MetricResult(
            name=self.name,
            score=round(efficiency, 3),
            passed=efficiency >= 0.40,
            reason=f"Reasoning efficiency score based on steps: {efficiency:.2f}."
        )


@MetricRegistry.register("tool_success_rate")
class ToolSuccessRateMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else {}
        total = metadata.get("total_tool_calls", 0)
        failures = metadata.get("tool_failures", 0)
        rate = 1.0
        if total > 0:
            rate = (total - failures) / total
        return MetricResult(
            name=self.name,
            score=round(rate, 3),
            passed=rate >= 0.90,
            reason=f"Tool success rate: {rate*100:.1f}% ({failures} failures out of {total} calls)."
        )


@MetricRegistry.register("tool_choice_correctness")
class ToolChoiceCorrectnessMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        actual_tools = actual_output if isinstance(actual_output, list) else []
        expected_tools = sample.expected_tools or []
        correct = True
        if expected_tools:
            correct = any(t in actual_tools for t in expected_tools)
        return MetricResult(
            name=self.name,
            score=1.0 if correct else 0.0,
            passed=correct,
            reason="Correct tool was executed." if correct else f"Expected tools: {expected_tools}, but got: {actual_tools}."
        )


@MetricRegistry.register("history_rewriting")
class HistoryRewritingMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        rewritten_query = str(actual_output) if actual_output else ""
        history = sample.conversation_history or []
        score = 1.0
        passed = True
        if history and sample.conversation_required:
            if not rewritten_query or rewritten_query.lower() == sample.question.lower():
                score = 0.0
                passed = False
            else:
                history_text = " ".join([h.get("content", "") for h in history])
                overlap = compute_word_overlap(rewritten_query, history_text)
                score = min(0.3 + (overlap * 0.7), 1.0)
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=passed,
            reason=f"History rewrite quality score: {score:.3f}."
        )


@MetricRegistry.register("context_budget_utilization")
class ContextBudgetMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        tokens_used = int(actual_output) if actual_output is not None else 0
        max_tokens = settings.MAX_CONTEXT_TOKENS
        ratio = tokens_used / max_tokens if max_tokens > 0 else 0.0
        return MetricResult(
            name=self.name,
            score=round(ratio, 3),
            passed=ratio <= 1.0,
            reason=f"Used {tokens_used} tokens out of max {max_tokens} limit ({ratio*100:.1f}%)."
        )
