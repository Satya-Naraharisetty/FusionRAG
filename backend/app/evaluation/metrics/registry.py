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
            raise KeyError(
                f"Metric '{name}' is not registered. Available: {list(cls._registry.keys())}"
            )
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
def calculate_relevance(
    retrieved: list[RetrievedContext], sample: EvaluationSample
) -> list[float]:
    """
    Calculates relevance score for each retrieved context.
    Supports graded relevance if sample.relevant_chunks is provided (e.g., 3.0, 2.0, 1.0),
    exact document/chunk ID matching, and ground truth text overlap.
    """
    relevance: list[float] = []
    expected_docs = [d.lower() for d in (sample.expected_documents or [])]
    gts = sample.ground_truth_context or []

    # Map graded chunk relevance if available
    graded_map: dict[str, float] = {}
    if sample.relevant_chunks:
        for rc in sample.relevant_chunks:
            doc_name = (
                rc.document.lower()
                if hasattr(rc, "document")
                else str(rc.get("document", "")).lower()
            )
            rel_val = float(
                rc.relevance if hasattr(rc, "relevance") else rc.get("relevance", 1.0)
            )
            if doc_name:
                graded_map[doc_name] = max(graded_map.get(doc_name, 1.0), rel_val)

    for c in retrieved:
        c_doc = (c.document_id or "").lower()
        c_chunk = (c.chunk_id or "").lower()
        c_text = (c.text or "").lower()

        # 1. Graded match by document or chunk ID or text containing doc name
        matched = False
        for doc_k, rel_v in graded_map.items():
            if (
                (c_doc and c_doc == doc_k)
                or (c_chunk and c_chunk == doc_k)
                or (doc_k in c_text)
            ):
                relevance.append(rel_v)
                matched = True
                break
        if matched:
            continue

        # 2. Binary match by expected_documents
        for exp_d in expected_docs:
            if (
                (c_doc and c_doc == exp_d)
                or (c_chunk and c_chunk == exp_d)
                or (exp_d in c_text)
            ):
                relevance.append(1.0)
                matched = True
                break
        if matched:
            continue

        # 3. Content overlap with ground truth context
        is_relevant = False
        rel_score = 0.0
        for gt in gts:
            gt_clean = gt.strip().lower()
            if len(gt_clean) > 8 and (gt_clean in c_text or c_text in gt_clean):
                is_relevant = True
                rel_score = 1.0
                break
            overlap = compute_word_overlap(c.text, gt)
            if overlap >= 0.35:
                is_relevant = True
                rel_score = 1.0
                break

        relevance.append(rel_score if is_relevant else 0.0)

    return relevance


# --- RETRIEVAL METRICS ---


@MetricRegistry.register("hit_rate")
class HitRateMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        is_neg_control = (
            sample.metadata.get("is_negative_control", False)
            or not sample.retrieval_required
        )

        if is_neg_control:
            # For negative controls, pass if no false-positive relevant context is claimed
            passed = len(retrieved_contexts) == 0 or not any(r > 0 for r in relevance)
            score = 1.0 if passed else 0.0
            reason = (
                "Negative control: no irrelevant context incorrectly flagged."
                if passed
                else "Negative control failed: irrelevant context flagged as relevant."
            )
        else:
            hit = 1.0 if any(r > 0 for r in relevance) else 0.0
            score = hit
            passed = hit > 0.0
            reason = (
                f"Hit found in top {len(retrieved_contexts)} retrieved chunks."
                if hit > 0
                else "No relevant context retrieved."
            )

        return MetricResult(name=self.name, score=score, passed=passed, reason=reason)


@MetricRegistry.register("precision_at_k")
class PrecisionAtKMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        is_neg_control = (
            sample.metadata.get("is_negative_control", False)
            or not sample.retrieval_required
        )

        if is_neg_control:
            precision = 1.0 if len(retrieved_contexts) == 0 else 0.0
        else:
            binary_rel = [1.0 if r > 0 else 0.0 for r in relevance]
            precision = sum(binary_rel) / len(binary_rel) if binary_rel else 0.0

        passed = precision >= settings.THRESHOLD_CONTEXT_PRECISION
        return MetricResult(
            name=self.name,
            score=round(precision, 3),
            passed=passed,
            reason=f"{sum(1 for r in relevance if r > 0)} out of {len(relevance)} retrieved chunks are relevant.",
        )


@MetricRegistry.register("recall_at_k")
class RecallAtKMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        is_neg_control = (
            sample.metadata.get("is_negative_control", False)
            or not sample.retrieval_required
        )

        if is_neg_control:
            # Negative control has 0 expected documents; recall is 1.0 if 0 retrieved or 0 relevant
            recall = 1.0
        else:
            expected_count = max(
                len(sample.relevant_chunks) if sample.relevant_chunks else 0,
                len(sample.expected_documents or []),
                len(sample.ground_truth_context or []),
                1,
            )
            found_count = sum(1 for r in relevance if r > 0)
            recall = min(found_count / expected_count, 1.0)

        passed = recall >= settings.THRESHOLD_CONTEXT_RECALL
        return MetricResult(
            name=self.name,
            score=round(recall, 3),
            passed=passed,
            reason=f"Found {sum(1 for r in relevance if r > 0)} relevant contexts out of required.",
        )


@MetricRegistry.register("mrr")
class MRRMetric(Metric):
    """
    Mean Reciprocal Rank (MRR): 1 / rank of the first relevant chunk retrieved.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        is_neg_control = (
            sample.metadata.get("is_negative_control", False)
            or not sample.retrieval_required
        )

        if is_neg_control:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="Negative control sample: MRR 1.0.",
            )

        mrr = 0.0
        rank = None
        for i, rel in enumerate(relevance):
            if rel > 0:
                mrr = 1.0 / (i + 1)
                rank = i + 1
                break

        passed = mrr >= 0.5  # First hit in top 2
        reason = (
            f"First relevant chunk at rank {rank} (MRR: {mrr:.3f})."
            if rank
            else "No relevant chunks retrieved."
        )
        return MetricResult(
            name=self.name, score=round(mrr, 3), passed=passed, reason=reason
        )


@MetricRegistry.register("ndcg")
class NDCGMetric(Metric):
    """
    Normalized Discounted Cumulative Gain (nDCG):
    Evaluates graded relevance ordering: DCG@k = sum((2^rel_i - 1) / log2(i + 2)) / IDCG@k
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        retrieved_contexts = actual_output if isinstance(actual_output, list) else []
        relevance = calculate_relevance(retrieved_contexts, sample)
        is_neg_control = (
            sample.metadata.get("is_negative_control", False)
            or not sample.retrieval_required
        )

        if is_neg_control:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="Negative control sample: nDCG 1.0.",
            )

        if not relevance or not any(r > 0 for r in relevance):
            return MetricResult(
                name=self.name,
                score=0.0,
                passed=False,
                reason="No relevant documents retrieved (nDCG 0.0).",
            )

        # Compute DCG
        dcg = sum(
            (math.pow(2, rel) - 1.0) / math.log2(i + 2)
            for i, rel in enumerate(relevance)
        )

        # Compute Ideal DCG (sorted descending)
        ideal_relevance = sorted(relevance, reverse=True)
        idcg = sum(
            (math.pow(2, rel) - 1.0) / math.log2(i + 2)
            for i, rel in enumerate(ideal_relevance)
        )

        ndcg_val = dcg / idcg if idcg > 0 else 0.0
        passed = ndcg_val >= 0.70
        return MetricResult(
            name=self.name,
            score=round(ndcg_val, 3),
            passed=passed,
            reason=f"nDCG score: {ndcg_val:.3f} (DCG: {dcg:.3f}, IDCG: {idcg:.3f}).",
        )


# --- CITATION QUALITY METRICS ---


@MetricRegistry.register("citation_validity")
class CitationValidityMetric(Metric):
    """
    Verifies that cited chunk/document IDs exist, were retrieved, and belong to the authorized scope.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        citations = actual_output if isinstance(actual_output, list) else []
        authorized_docs = sample.metadata.get("document_ids") or (
            sample.expected_documents or []
        )
        unauth_list = [
            str(u).lower()
            for u in sample.metadata.get("unauthorized_scope_citations", [])
        ]

        if not citations:
            score = 1.0 if not sample.expected_citations else 0.0
            return MetricResult(
                name=self.name,
                score=score,
                passed=score >= 0.8,
                reason="No citations produced."
                if not sample.expected_citations
                else "Expected citations but none found.",
            )

        valid_count = 0
        for cite in citations:
            doc_id = (
                str(
                    cite.get("document_id")
                    or cite.get("document_name")
                    or cite.get("source_id")
                    or ""
                )
                if isinstance(cite, dict)
                else str(
                    getattr(cite, "document_name", "")
                    or getattr(cite, "document_id", "")
                    or getattr(cite, "source_id", "")
                )
            )

            # Explicit unauth check
            if doc_id and doc_id.lower() in unauth_list:
                continue

            # Scope authorization check
            if authorized_docs and doc_id:
                if str(doc_id).lower() not in [str(d).lower() for d in authorized_docs]:
                    continue  # Unauthorized document citation

            valid_count += 1

        score = valid_count / len(citations) if citations else 1.0
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.9,
            reason=f"{valid_count} of {len(citations)} citations are valid and authorized.",
        )


@MetricRegistry.register("citation_precision")
class CitationPrecisionMetric(Metric):
    """
    Ratio of citations that correctly reference retrieved, authorized evidence to total citations produced.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        citations = actual_output if isinstance(actual_output, list) else []
        expected_citations = (
            sample.expected_citations or sample.expected_documents or []
        )
        unauth_list = [
            str(u).lower()
            for u in sample.metadata.get("unauthorized_scope_citations", [])
        ]

        if not citations:
            score = 1.0 if not expected_citations else 0.0
            return MetricResult(
                name=self.name,
                score=score,
                passed=score >= 0.8,
                reason="Zero citations produced.",
            )

        correct_citations = 0
        for cite in citations:
            doc_id = (
                str(
                    cite.get("document_name")
                    or cite.get("document_id")
                    or cite.get("source_id")
                    or ""
                )
                if isinstance(cite, dict)
                else str(
                    getattr(cite, "document_name", "")
                    or getattr(cite, "document_id", "")
                    or getattr(cite, "source_id", "")
                )
            )

            if doc_id and doc_id.lower() in unauth_list:
                continue

            if any(
                str(exp).lower() in doc_id.lower() or doc_id.lower() in str(exp).lower()
                for exp in expected_citations
            ):
                correct_citations += 1

        score = correct_citations / len(citations)
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.85,
            reason=f"Citation precision: {correct_citations}/{len(citations)} match expected evidence.",
        )


@MetricRegistry.register("citation_grounding")
class CitationGroundingMetric(Metric):
    """
    Verifies that the cited evidence content actually supports the corresponding answer claim.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        actual_answer = str(sample.metadata.get("actual_answer") or "")
        citations = actual_output if isinstance(actual_output, list) else []

        if not citations:
            return MetricResult(
                name=self.name,
                score=1.0 if not sample.retrieval_required else 0.0,
                passed=not sample.retrieval_required,
                reason="No citations to ground answer claims."
                if sample.retrieval_required
                else "No citations required.",
            )

        grounded_citations = 0
        for cite in citations:
            snippet = (
                str(
                    cite.get("content") or cite.get("snippet") or cite.get("text") or ""
                )
                if isinstance(cite, dict)
                else str(
                    getattr(cite, "content", "")
                    or getattr(cite, "snippet", "")
                    or getattr(cite, "text", "")
                )
            )

            if not snippet:
                grounded_citations += 1
                continue
            # Measure token/word overlap between cited snippet and answer
            overlap = compute_word_overlap(snippet, actual_answer)
            if overlap >= 0.20 or any(
                w in actual_answer.lower()
                for w in snippet.lower().split()
                if len(w) > 4
            ):
                grounded_citations += 1

        score = grounded_citations / len(citations)
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.80,
            reason=f"Citation grounding score: {score * 100:.1f}% ({grounded_citations}/{len(citations)} grounded).",
        )


@MetricRegistry.register("citation_coverage")
class CitationCoverageMetric(Metric):
    """
    Measures the proportion of answer claims/key assertions that have supporting citations.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        citations = actual_output if isinstance(actual_output, list) else []
        actual_answer = str(sample.metadata.get("actual_answer") or "")

        if not sample.retrieval_required:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="No retrieval required for this sample.",
            )

        if not actual_answer or not citations:
            score = 0.0 if sample.retrieval_required else 1.0
            return MetricResult(
                name=self.name,
                score=score,
                passed=score >= 0.7,
                reason="Answer lacks citations for required retrieval.",
            )

        # Estimate sentences / assertions in answer
        sentences = [s.strip() for s in actual_answer.split(".") if len(s.strip()) > 15]
        if not sentences:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="Answer too concise to require multi-citation coverage.",
            )

        # Match each sentence with cited evidence
        covered = 0
        for sentence in sentences:
            if any(
                compute_word_overlap(
                    str(
                        c.get("content", "") or c.get("text", "")
                        if isinstance(c, dict)
                        else getattr(c, "content", "") or getattr(c, "text", "")
                    ),
                    sentence,
                )
                >= 0.15
                for c in citations
            ):
                covered += 1

        coverage = min(
            max(covered / len(sentences), len(citations) / len(sentences)), 1.0
        )
        return MetricResult(
            name=self.name,
            score=round(coverage, 3),
            passed=coverage >= 0.70,
            reason=f"Citation coverage: {coverage * 100:.1f}% of key claims backed by citations.",
        )


# --- MULTI-AGENT OBSERVABLE METRICS ---


@MetricRegistry.register("task_success_rate")
class TaskSuccessRateMetric(Metric):
    """
    Ratio of planned tasks that completed successfully with a valid observable result to total planned tasks.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else sample.metadata
        total_tasks = (
            metadata.get("total_tasks")
            or len(metadata.get("planned_tasks", []))
            or metadata.get("initial_task_count")
            or 1
        )
        completed_tasks = (
            metadata.get("successful_tasks_count")
            or len(metadata.get("completed_tasks", []))
            or metadata.get("successful_task_count")
            or total_tasks
        )
        failed_tasks = metadata.get("failed_tasks_count") or len(
            metadata.get("failed_tasks", [])
        )

        rate = (
            max(0.0, (total_tasks - failed_tasks) / total_tasks)
            if total_tasks > 0
            else 1.0
        )
        return MetricResult(
            name=self.name,
            score=round(rate, 3),
            passed=rate >= 0.85,
            reason=f"Task success rate: {rate * 100:.1f}% ({completed_tasks}/{total_tasks} tasks successful).",
        )


@MetricRegistry.register("evidence_sufficiency_rate")
class EvidenceSufficiencyRateMetric(Metric):
    """
    Ratio of completed research tasks whose retrieved evidence satisfies observable evidence requirements.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else sample.metadata
        research_total = (
            metadata.get("research_tasks_total")
            or metadata.get("research_evidence_count")
            or len(metadata.get("evidence", []))
        )
        research_sufficient = (
            metadata.get("research_tasks_sufficient")
            if "research_tasks_sufficient" in metadata
            else (research_total - metadata.get("unsupported_evidence_count", 0))
        )

        rate = 1.0
        if research_total and float(research_total) > 0:
            suff_val = (
                float(research_sufficient) if research_sufficient is not None else 0.0
            )
            rate = max(0.0, min(1.0, suff_val / float(research_total)))
        elif sample.retrieval_required and not sample.ground_truth_context:
            rate = 1.0

        return MetricResult(
            name=self.name,
            score=round(rate, 3),
            passed=rate >= 0.80,
            reason=f"Evidence sufficiency rate: {rate * 100:.1f}%.",
        )


@MetricRegistry.register("replan_success_rate")
class ReplanSuccessRateMetric(Metric):
    """
    Ratio of replanning iterations that resolved missing evidence/failures into successful downstream synthesis.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else sample.metadata
        replans = metadata.get("replans") or metadata.get("number_of_replans") or 0
        synthesis_success = metadata.get("synthesis_success", True)

        if replans == 0:
            rate = 1.0
            reason = "No replanning was required (first plan succeeded)."
        else:
            rate = 1.0 if synthesis_success else 0.0
            reason = f"Replanning occurred ({replans} iterations) and synthesis {'succeeded' if synthesis_success else 'failed'}."

        return MetricResult(
            name=self.name, score=round(rate, 3), passed=rate >= 0.80, reason=reason
        )


@MetricRegistry.register("duplicate_task_avoidance")
class DuplicateTaskAvoidanceMetric(Metric):
    """
    1 - (duplicate task executions / total task executions)
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else sample.metadata
        total_tasks = (
            metadata.get("total_tasks") or metadata.get("final_task_count") or 1
        )
        avoided_duplicates = metadata.get("avoided_duplicate_tasks", 0)
        duplicates = metadata.get("duplicate_tasks_executed", 0)

        rate = 1.0 - (duplicates / total_tasks) if total_tasks > 0 else 1.0
        rate = max(0.0, min(1.0, rate))
        return MetricResult(
            name=self.name,
            score=round(rate, 3),
            passed=rate >= 0.90,
            reason=f"Duplicate task avoidance: {rate * 100:.1f}% ({avoided_duplicates} duplicates avoided).",
        )


@MetricRegistry.register("agent_call_efficiency")
class AgentCallEfficiencyMetric(Metric):
    """
    Ratio of successful task-producing agent calls to total agent calls, excluding infrastructure calls.
    """

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        metadata = actual_output if isinstance(actual_output, dict) else sample.metadata
        total_calls = (
            metadata.get("total_agent_calls")
            or metadata.get("total_specialist_calls")
            or 1
        )
        successful_calls = (
            metadata.get("successful_task_count")
            or metadata.get("successful_tasks_count")
            or total_calls
        )

        efficiency = successful_calls / total_calls if total_calls > 0 else 1.0
        efficiency = min(max(efficiency, 0.0), 1.0)
        return MetricResult(
            name=self.name,
            score=round(efficiency, 3),
            passed=efficiency >= 0.70,
            reason=f"Agent call efficiency: {efficiency * 100:.1f}% ({successful_calls}/{total_calls} productive calls).",
        )


# --- REASONING & CONVERSATION METRICS ---


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
            reason=f"Executed {steps} reasoning steps. Limit: {settings.MAX_TOOL_ITERATIONS}.",
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
        return MetricResult(name=self.name, score=score, passed=passed, reason=reason)


@MetricRegistry.register("tool_ordering")
class ToolOrderingMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        actual_tools = actual_output if isinstance(actual_output, list) else []
        expected_tools = sample.expected_tools or []
        score = 1.0
        if expected_tools and actual_tools:
            matches = sum(
                1
                for idx, tool in enumerate(actual_tools)
                if idx < len(expected_tools) and tool == expected_tools[idx]
            )
            score = matches / max(len(expected_tools), len(actual_tools))
        elif expected_tools and not actual_tools:
            score = 0.0
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.70,
            reason=f"Tool calling order similarity: {score * 100:.1f}%.",
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
            reason=f"Reasoning efficiency score based on steps: {efficiency:.2f}.",
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
            reason=f"Tool success rate: {rate * 100:.1f}% ({failures} failures out of {total} calls).",
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
            reason="Correct tool was executed."
            if correct
            else f"Expected tools: {expected_tools}, but got: {actual_tools}.",
        )


@MetricRegistry.register("history_rewriting")
class HistoryRewritingMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        rewritten_query = str(actual_output) if actual_output else ""
        history = sample.conversation_history or []
        score = 1.0
        passed = True
        if history and sample.conversation_required:
            if (
                not rewritten_query
                or rewritten_query.lower() == sample.question.lower()
            ):
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
            reason=f"History rewrite quality score: {score:.3f}.",
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
            reason=f"Used {tokens_used} tokens out of max {max_tokens} limit ({ratio * 100:.1f}%).",
        )


@MetricRegistry.register("context_recall")
class ContextRecallMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        contexts: list[RetrievedContext] = (
            actual_output if isinstance(actual_output, list) else []
        )
        gts = sample.ground_truth_context or []
        if not gts:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="No ground truth context specified.",
            )

        combined_text = " ".join(
            [c.text for c in contexts if hasattr(c, "text") and c.text]
        )
        if not combined_text:
            return MetricResult(
                name=self.name, score=0.0, passed=False, reason="No context retrieved."
            )

        hits = 0
        for gt in gts:
            overlap = compute_word_overlap(gt, combined_text)
            if overlap >= 0.25:
                hits += 1

        score = hits / len(gts)
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.70,
            reason=f"Context recall: {hits}/{len(gts)} ground truth statements covered ({score * 100:.1f}%).",
        )


@MetricRegistry.register("context_precision")
class ContextPrecisionMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        contexts: list[RetrievedContext] = (
            actual_output if isinstance(actual_output, list) else []
        )
        if not contexts:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                reason="No contexts to evaluate.",
            )

        relevances = calculate_relevance(contexts, sample)
        relevant_count = sum(1 for r in relevances if r > 0.0)
        score = relevant_count / len(contexts)
        return MetricResult(
            name=self.name,
            score=round(score, 3),
            passed=score >= 0.50,
            reason=f"Context precision: {relevant_count}/{len(contexts)} chunks relevant ({score * 100:.1f}%).",
        )


@MetricRegistry.register("duplicate_context_rate")
class DuplicateContextRateMetric(Metric):
    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        contexts: list[RetrievedContext] = (
            actual_output if isinstance(actual_output, list) else []
        )
        if not contexts:
            return MetricResult(
                name=self.name, score=0.0, passed=True, reason="No duplicate context."
            )

        chunk_ids = [c.chunk_id for c in contexts if c.chunk_id]
        if not chunk_ids:
            return MetricResult(
                name=self.name, score=0.0, passed=True, reason="Zero duplicates found."
            )

        unique_count = len(set(chunk_ids))
        duplicate_count = len(chunk_ids) - unique_count
        rate = duplicate_count / len(chunk_ids)
        return MetricResult(
            name=self.name,
            score=round(rate, 3),
            passed=rate == 0.0,
            reason=f"Duplicate context rate: {rate * 100:.1f}% ({duplicate_count} duplicates).",
        )
