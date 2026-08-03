from typing import Any, Protocol
from app.evaluation.domain.models import EvaluationSample, EvaluationResult


class EvaluationProvider(Protocol):
    """
    Interface for LLM-backed evaluation engines (e.g., Ragas, DeepEval).
    Supports offline evaluations and mock/stub mode.
    """
    async def evaluate(
        self,
        samples: list[EvaluationSample],
        metrics: list[str],
        mock: bool = False
    ) -> list[EvaluationResult]:
        """
        Evaluate a batch of samples against specified metrics.
        """
        ...
