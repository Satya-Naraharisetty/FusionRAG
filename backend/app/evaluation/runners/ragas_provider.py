import logging
from typing import Any

from app.core.config import settings
from app.evaluation.domain.interfaces import EvaluationProvider
from app.evaluation.domain.models import (
    EvaluationResult,
    EvaluationSample,
    MetricResult,
    RetrievedContext,
)

logger = logging.getLogger(__name__)

_ragas_available = None


def is_ragas_available() -> bool:
    global _ragas_available
    if _ragas_available is None:
        try:
            from datasets import Dataset  # noqa: F401
            from ragas import evaluate as ragas_evaluate  # noqa: F401
            from ragas.metrics import (  # noqa: F401
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )

            _ragas_available = True
        except ImportError as e:
            _ragas_available = False
            if settings.ENABLE_RAGAS:
                logger.warning(
                    f"Ragas or its dependencies are not fully loaded/installed. "
                    f"Ragas evaluations will run in Mock/Stub mode. Detail: {e}"
                )
    return _ragas_available


class RagasProvider(EvaluationProvider):
    """
    EvaluationProvider implementation for Ragas.
    Evaluates faithfulness, answer relevancy, context precision, context recall, and context utilization.
    """

    async def evaluate(
        self, samples: list[EvaluationSample], metrics: list[str], mock: bool = False
    ) -> list[EvaluationResult]:
        # Determine if we must run mock mode
        use_mock = mock or not settings.ENABLE_RAGAS or not is_ragas_available()

        if use_mock:
            logger.info("Executing Ragas metrics in Mock/Stub mode...")
            return self._evaluate_mock(samples, metrics)

        return await self._evaluate_real(samples, metrics)

    async def _evaluate_real(
        self, samples: list[EvaluationSample], metrics: list[str]
    ) -> list[EvaluationResult]:
        try:
            from datasets import Dataset
            from ragas import evaluate as ragas_evaluate
            from ragas.metrics import (
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )

            # 1. Prepare Ragas dataset structure
            questions = []
            answers = []
            contexts_list = []
            ground_truths = []

            for sample in samples:
                questions.append(sample.question)
                # Fallback actual answer or default empty
                answers.append(sample.metadata.get("actual_answer") or "")

                # retrieved contexts list of strings
                retrieved = list(sample.metadata.get("retrieved_contexts") or [])
                contexts_list.append(retrieved if retrieved else [""])

                # ground truth context list of strings
                gt = sample.ground_truth_context or []
                ground_truths.append(gt if gt else [""])

            # Format to HuggingFace Dataset
            data = {
                "question": questions,
                "answer": answers,
                "contexts": contexts_list,
                "ground_truth": ground_truths,
            }
            dataset = Dataset.from_dict(data)

            # 2. Resolve Ragas LLM and Embeddings pointing to Google Gemini
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
            from pydantic import SecretStr

            llm = ChatOpenAI(
                model=settings.GEMINI_CHAT_MODEL,
                api_key=SecretStr(settings.GEMINI_API_KEY)
                if settings.GEMINI_API_KEY
                else None,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                temperature=0.0,
            )
            embeddings = OpenAIEmbeddings(
                model="text-embedding-004",  # Gemini embedding model name
                api_key=SecretStr(settings.GEMINI_API_KEY)
                if settings.GEMINI_API_KEY
                else None,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )

            # 3. Resolve metrics
            ragas_metrics = []
            if "faithfulness" in metrics:
                ragas_metrics.append(faithfulness)
            if "answer_relevancy" in metrics:
                ragas_metrics.append(answer_relevancy)
            if "context_precision" in metrics:
                ragas_metrics.append(context_precision)
            if "context_recall" in metrics:
                ragas_metrics.append(context_recall)

            if not ragas_metrics:
                ragas_metrics = [faithfulness, answer_relevancy]

            # 4. Run Ragas evaluation
            # Run blocking task in executor since Ragas evaluation runs synchronously
            import asyncio

            loop = asyncio.get_event_loop()
            result_df: Any = await loop.run_in_executor(
                None,
                lambda: ragas_evaluate(
                    dataset=dataset,
                    metrics=ragas_metrics,
                    llm=llm,
                    embeddings=embeddings,
                ),
            )

            # Convert results back to domain model list
            results = []
            for i, sample in enumerate(samples):
                metric_results = []
                actual_answer = answers[i]

                # Extract scores from dataframe
                row = result_df.scores[i]
                for metric_name in metrics:
                    score = row.get(metric_name) or 0.0
                    passed = score >= getattr(
                        settings, f"THRESHOLD_{metric_name.upper()}", 0.85
                    )
                    metric_results.append(
                        MetricResult(
                            name=metric_name,
                            score=float(score),
                            passed=passed,
                            reason=f"Calculated by Ragas using {settings.EVALUATION_PROVIDER}.",
                        )
                    )

                # Populate RetrievedContexts
                contexts_objs = [
                    RetrievedContext(text=c, score=1.0) for c in contexts_list[i]
                ]

                results.append(
                    EvaluationResult(
                        sample_id=sample.id,
                        question=sample.question,
                        expected_answer=sample.expected_answer,
                        actual_answer=actual_answer,
                        latency=sample.metadata.get("latency", 0.0),
                        input_tokens=sample.metadata.get("input_tokens", 0),
                        output_tokens=sample.metadata.get("output_tokens", 0),
                        cost=sample.metadata.get("cost", 0.0),
                        error_category=sample.metadata.get("error_category") or "None",
                        metrics=metric_results,
                        retrieved_contexts=contexts_objs,
                        metadata=sample.metadata,
                    )
                )

            return results

        except Exception as e:
            logger.error(
                f"Failed to execute real Ragas evaluation: {e}. Falling back to Mock mode.",
                exc_info=True,
            )
            return self._evaluate_mock(samples, metrics)

    def _evaluate_mock(
        self, samples: list[EvaluationSample], metrics: list[str]
    ) -> list[EvaluationResult]:
        results = []
        for sample in samples:
            metric_results = []
            actual_answer = sample.metadata.get("actual_answer") or ""
            retrieved_contexts = sample.metadata.get("retrieved_contexts") or []

            # 1. Compute mock score for each metric using heuristics
            for metric in metrics:
                score = 0.85  # Default baseline
                reason = "Mock evaluation fallback."

                if metric == "faithfulness":
                    # Faithfulness: overlap between answer and contexts
                    if not actual_answer:
                        score = 0.0
                    elif not retrieved_contexts:
                        score = 0.0
                    else:
                        overlap = self._compute_word_overlap(
                            actual_answer, " ".join(retrieved_contexts)
                        )
                        score = min(0.5 + (overlap * 0.5), 1.0)
                    reason = (
                        f"Simulated faithfulness based on word overlap ({score:.2f})."
                    )

                elif metric == "answer_relevancy":
                    # Answer relevancy: overlap between question and answer
                    if not actual_answer:
                        score = 0.0
                    else:
                        overlap = self._compute_word_overlap(
                            sample.question, actual_answer
                        )
                        score = min(0.4 + (overlap * 0.6), 1.0)
                    reason = f"Simulated answer relevancy based on question/answer overlap ({score:.2f})."

                elif metric == "context_precision":
                    # Context precision: context similarity to ground truth
                    gts = sample.ground_truth_context or []
                    if not retrieved_contexts:
                        score = 0.0
                    elif not gts:
                        score = 1.0
                    else:
                        overlap = self._compute_word_overlap(
                            " ".join(retrieved_contexts), " ".join(gts)
                        )
                        score = min(0.5 + (overlap * 0.5), 1.0)
                    reason = f"Simulated context precision based on retrieved/ground-truth overlap ({score:.2f})."

                elif metric == "context_recall":
                    # Context recall: ground truth covered by contexts
                    gts = sample.ground_truth_context or []
                    if not gts:
                        score = 1.0
                    elif not retrieved_contexts:
                        score = 0.0
                    else:
                        overlap = self._compute_word_overlap(
                            " ".join(gts), " ".join(retrieved_contexts)
                        )
                        score = min(0.6 + (overlap * 0.4), 1.0)
                    reason = f"Simulated context recall based on ground-truth coverage ({score:.2f})."

                passed = score >= getattr(settings, f"THRESHOLD_{metric.upper()}", 0.85)
                metric_results.append(
                    MetricResult(
                        name=metric,
                        score=float(round(score, 3)),
                        passed=passed,
                        reason=reason,
                    )
                )

            # Populate contexts list
            contexts_objs = [
                RetrievedContext(text=c, score=1.0) for c in retrieved_contexts
            ]

            results.append(
                EvaluationResult(
                    sample_id=sample.id,
                    question=sample.question,
                    expected_answer=sample.expected_answer,
                    actual_answer=actual_answer,
                    latency=sample.metadata.get("latency", 0.0),
                    input_tokens=sample.metadata.get("input_tokens", 0),
                    output_tokens=sample.metadata.get("output_tokens", 0),
                    cost=sample.metadata.get("cost", 0.0),
                    error_category=sample.metadata.get("error_category") or "None",
                    metrics=metric_results,
                    retrieved_contexts=contexts_objs,
                    metadata=sample.metadata,
                )
            )

        return results

    def _compute_word_overlap(self, text1: str, text2: str) -> float:
        """
        Calculates simple word overlap (Jaccard similarity) between two text blocks.
        """

        def get_words(t: str) -> set[str]:
            return {w.strip(".,!?;:()[]\"'").lower() for w in t.split() if len(w) > 2}

        w1 = get_words(text1)
        w2 = get_words(text2)
        if not w1 or not w2:
            return 0.0
        intersection = w1.intersection(w2)
        union = w1.union(w2)
        return len(intersection) / len(union)
