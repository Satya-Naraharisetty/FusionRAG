from typing import Any
from app.evaluation.domain.models import EvaluationSample, MetricResult


class Metric:
    """
    Abstract base class for all evaluation metrics.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def evaluate(self, sample: EvaluationSample, actual_output: Any) -> MetricResult:
        """
        Evaluate a single sample and return a MetricResult.
        """
        raise NotImplementedError()
