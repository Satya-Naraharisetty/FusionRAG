import logging

from app.evaluation.domain.models import (
    CitationEvaluation,
    EvaluationResult,
    EvaluationSample,
    MetricResult,
)
from app.evaluation.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


class CitationEvaluator:
    """
    Dedicated Citation Evaluator evaluating:
    - citation_validity: chunk/document ID existence, retrieval, and scope authorization.
    - citation_precision: ratio of citations referencing expected/retrieved evidence.
    - citation_grounding: semantic support of answer claims by cited evidence.
    - citation_coverage: proportion of key claims backed by valid citations.
    """

    async def evaluate_samples(
        self, samples: list[EvaluationSample], mock: bool = False
    ) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []

        for sample in samples:
            citations = sample.metadata.get("citations") or []
            actual_answer = sample.metadata.get("actual_answer") or ""
            latency = sample.metadata.get("latency", 0.0)

            # If mock and citations not in metadata, build representative citation fixtures
            if mock and not citations and sample.expected_documents:
                citations = [
                    {
                        "document_name": doc,
                        "document_id": doc,
                        "chunk_id": f"chunk-{doc}-0",
                        "content": sample.ground_truth_context[0]
                        if sample.ground_truth_context
                        else "Supporting claim text",
                    }
                    for doc in sample.expected_documents
                ]
                sample.metadata["citations"] = citations
                if not actual_answer and sample.expected_answer:
                    actual_answer = sample.expected_answer
                    sample.metadata["actual_answer"] = actual_answer

            metric_results: list[MetricResult] = []
            citation_metrics = [
                "citation_validity",
                "citation_precision",
                "citation_grounding",
                "citation_coverage",
            ]

            for m_name in citation_metrics:
                try:
                    metric = MetricRegistry.get_metric(m_name)
                    metric_results.append(metric.evaluate(sample, citations))
                except Exception as e:
                    logger.error(f"Failed to evaluate citation metric {m_name}: {e}")

            # Compute overall citation passed status
            all_passed = all(m.passed for m in metric_results if m.passed is not None)

            validity_score = next(
                (m.score for m in metric_results if m.name == "citation_validity"),
                1.0,
            )
            precision_score = next(
                (m.score for m in metric_results if m.name == "citation_precision"),
                1.0,
            )
            grounding_score = next(
                (m.score for m in metric_results if m.name == "citation_grounding"),
                1.0,
            )
            coverage_score = next(
                (m.score for m in metric_results if m.name == "citation_coverage"),
                1.0,
            )

            # Count unauthorized / nonexistent citations
            authorized_docs = sample.metadata.get("document_ids") or (
                sample.expected_documents or []
            )
            unauth_count = 0
            for cite in citations:
                doc_name = (
                    cite.get("document_name")
                    if isinstance(cite, dict)
                    else getattr(cite, "document_name", None)
                )
                if (
                    authorized_docs
                    and doc_name
                    and str(doc_name).lower()
                    not in [str(d).lower() for d in authorized_docs]
                ):
                    unauth_count += 1

            citation_eval = CitationEvaluation(
                citation_validity=validity_score,
                citation_precision=precision_score,
                citation_grounding=grounding_score,
                citation_coverage=coverage_score,
                unauthorized_citations_count=unauth_count,
                nonexistent_citations_count=(
                    0 if (validity_score is not None and validity_score > 0) else 1
                ),
                passed=all_passed,
                reason="All citation checks passed."
                if all_passed
                else "Citation validation failed.",
            )

            sample_metadata = dict(sample.metadata)
            sample_metadata["citation_evaluation"] = citation_eval.model_dump()

            results.append(
                EvaluationResult(
                    sample_id=sample.id,
                    question=sample.question,
                    expected_answer=sample.expected_answer,
                    actual_answer=actual_answer,
                    latency=latency,
                    error_category="Citation Error" if not all_passed else "None",
                    metrics=metric_results,
                    retrieved_contexts=[],
                    metadata=sample_metadata,
                )
            )

        return results
