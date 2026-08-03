import logging
import time
from typing import Any

from app.evaluation.domain.models import EvaluationSample, EvaluationResult, RetrievedContext
from app.documents.services.retrieval_service import RetrievalService
from app.evaluation.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


class RetrievalEvaluator:
    """
    Retrieval Evaluator that runs search queries and executes metrics
    obtained from the MetricRegistry against retrieved chunks.
    """

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    async def evaluate_samples(
        self,
        samples: list[EvaluationSample],
        top_k: int = 10,
        mock: bool = False
    ) -> list[EvaluationResult]:
        results = []

        for sample in samples:
            start_time = time.perf_counter()
            retrieved_chunks = []

            # 1. Execute retrieval
            if mock:
                latency = 0.05
                gts = sample.ground_truth_context or []
                for i, gt in enumerate(gts[:3]):
                    retrieved_chunks.append({
                        "text": gt,
                        "score": 0.85 - (i * 0.05),
                        "chunk_id": f"chunk-gt-{i}",
                        "document_id": sample.expected_documents[i] if sample.expected_documents and i < len(sample.expected_documents) else f"doc-gt-{i}"
                    })
                retrieved_chunks.append({
                    "text": "This is a random unrelated document text chunk for search noise.",
                    "score": 0.35,
                    "chunk_id": "chunk-noise",
                    "document_id": "doc-noise"
                })
            else:
                try:
                    filters = sample.metadata.get("filters")
                    document_ids = sample.metadata.get("document_ids")
                    
                    chunks = await self.retrieval_service.retrieve(
                        query=sample.question,
                        top_k=top_k,
                        document_ids=document_ids,
                        filters=filters
                    )
                    
                    for c in chunks:
                        retrieved_chunks.append({
                            "text": c.text,
                            "score": c.score if hasattr(c, "score") else 1.0,
                            "chunk_id": str(c.id) if hasattr(c, "id") else "",
                            "document_id": str(c.document_id) if hasattr(c, "document_id") else ""
                        })
                except Exception as e:
                    logger.error(f"Retrieval failed for sample {sample.id}: {e}")

            latency = time.perf_counter() - start_time

            # Convert chunks to RetrievedContext
            retrieved_contexts = [
                RetrievedContext(
                    text=c["text"],
                    score=c["score"],
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"]
                )
                for c in retrieved_chunks
            ]

            # 2. Evaluate using registered metrics
            metric_results = []
            retrieval_metrics = ["hit_rate", "precision_at_k", "recall_at_k", "mrr", "ndcg"]
            
            for m_name in retrieval_metrics:
                try:
                    metric = MetricRegistry.get_metric(m_name)
                    metric_results.append(metric.evaluate(sample, retrieved_contexts))
                except Exception as e:
                    logger.error(f"Failed to evaluate metric {m_name}: {e}")

            # Check if hit rate passed
            hit_passed = any(m.passed for m in metric_results if m.name == "hit_rate")
            error_category = "None"
            if not hit_passed and sample.retrieval_required:
                error_category = "Retrieval Failure"

            sample_metadata = dict(sample.metadata)
            sample_metadata["retrieved_contexts"] = [c.text for c in retrieved_contexts]
            sample_metadata["latency"] = latency
            sample_metadata["error_category"] = error_category

            results.append(EvaluationResult(
                sample_id=sample.id,
                question=sample.question,
                expected_answer=sample.expected_answer,
                latency=latency,
                error_category=error_category,
                metrics=metric_results,
                retrieved_contexts=retrieved_contexts,
                metadata=sample_metadata
            ))

        return results
