import inspect
import json
import logging
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.evaluation.domain.models import BaselineData, RegressionRun
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun

logger = logging.getLogger(__name__)


class RegressionRunner:
    """
    Regression Runner evaluates performance differences between a candidate benchmark run
    and an approved baseline (from DB or baseline_v1.json), flagging regressions based on configurable thresholds.
    """

    EVALUATOR_VERSION = "v1"

    async def compare_runs(
        self,
        db: AsyncSession,
        candidate_run_id: uuid.UUID,
        baseline_run_id: uuid.UUID,
        delta_thresholds: dict[str, float] | None = None,
        max_score_drop: float = 0.03,
        max_latency_increase_percent: float = 20.0,
    ) -> RegressionRun:
        """
        Compare candidate run scores with baseline run scores in database.
        """
        cand_stmt = (
            select(SQLAlchemyEvaluationRun)
            .options(selectinload(SQLAlchemyEvaluationRun.results))
            .where(SQLAlchemyEvaluationRun.id == candidate_run_id)
        )
        candidate_result: Any = db.execute(cand_stmt)
        if inspect.isawaitable(candidate_result):
            candidate_result = await candidate_result
        candidate = candidate_result.scalar_one_or_none()

        base_stmt = (
            select(SQLAlchemyEvaluationRun)
            .options(selectinload(SQLAlchemyEvaluationRun.results))
            .where(SQLAlchemyEvaluationRun.id == baseline_run_id)
        )
        baseline_result: Any = db.execute(base_stmt)
        if inspect.isawaitable(baseline_result):
            baseline_result = await baseline_result
        baseline = baseline_result.scalar_one_or_none()

        if not candidate:
            raise ValueError(
                f"Candidate run ID {candidate_run_id} not found in database."
            )
        if not baseline:
            raise ValueError(
                f"Baseline run ID {baseline_run_id} not found in database."
            )

        # Baseline Compatibility Check
        self._check_run_compatibility(candidate, baseline)

        candidate_averages = self._calculate_average_metrics(candidate)
        baseline_averages = self._calculate_average_metrics(baseline)

        return self._evaluate_metrics_delta(
            candidate_run_id=candidate_run_id,
            baseline_run_id=baseline_run_id,
            candidate_metrics=candidate_averages,
            baseline_metrics=baseline_averages,
            candidate_latency=candidate.avg_latency,
            baseline_latency=baseline.avg_latency,
            delta_thresholds=delta_thresholds,
            max_score_drop=max_score_drop,
            max_latency_increase_percent=max_latency_increase_percent,
        )

    def compare_with_baseline_data(
        self,
        candidate_metrics: dict[str, float],
        candidate_latency: float,
        baseline: BaselineData,
        candidate_dataset_version: str = "1.0.0",
        candidate_profile: str = "fast_deterministic",
        candidate_run_id: uuid.UUID | None = None,
        delta_thresholds: dict[str, float] | None = None,
        max_score_drop: float = 0.03,
        max_latency_increase_percent: float = 20.0,
        ignore_profile_mismatch: bool = False,
        ignore_dataset_mismatch: bool = False,
    ) -> RegressionRun:
        """
        Compare candidate metrics against an approved BaselineData object (e.g. from baseline_v1.json).
        """
        # Baseline Compatibility Check
        if (
            not ignore_dataset_mismatch
            and baseline.dataset_version != candidate_dataset_version
        ):
            raise ValueError(
                f"Baseline dataset version mismatch: baseline '{baseline.dataset_version}' vs candidate '{candidate_dataset_version}'."
            )
        if not ignore_profile_mismatch and baseline.profile != candidate_profile:
            raise ValueError(
                f"Baseline profile mismatch: baseline '{baseline.profile}' vs candidate '{candidate_profile}'."
            )
        if baseline.evaluator_version != self.EVALUATOR_VERSION:
            raise ValueError(
                f"Baseline evaluator version incompatible: baseline '{baseline.evaluator_version}' vs expected '{self.EVALUATOR_VERSION}'."
            )

        baseline_latency = baseline.latency_metrics.get("avg_latency", 0.0)

        return self._evaluate_metrics_delta(
            candidate_run_id=candidate_run_id or uuid.uuid4(),
            baseline_run_id=uuid.UUID(int=0),
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline.metric_averages,
            candidate_latency=candidate_latency,
            baseline_latency=baseline_latency,
            delta_thresholds=delta_thresholds,
            max_score_drop=max_score_drop,
            max_latency_increase_percent=max_latency_increase_percent,
        )

    def load_baseline_file(self, file_path: str) -> BaselineData:
        """
        Load BaselineData from a JSON baseline artifact file.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Baseline file not found: {file_path}")
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            return BaselineData(**data)

    def _check_run_compatibility(
        self, candidate: SQLAlchemyEvaluationRun, baseline: SQLAlchemyEvaluationRun
    ) -> None:
        if candidate.dataset_version != baseline.dataset_version:
            raise ValueError(
                f"Incompatible dataset versions: Candidate v{candidate.dataset_version} vs Baseline v{baseline.dataset_version}."
            )
        if candidate.profile != baseline.profile:
            raise ValueError(
                f"Incompatible evaluation profiles: Candidate '{candidate.profile}' vs Baseline '{baseline.profile}'."
            )

    def _evaluate_metrics_delta(
        self,
        candidate_run_id: uuid.UUID,
        baseline_run_id: uuid.UUID,
        candidate_metrics: dict[str, float],
        baseline_metrics: dict[str, float],
        candidate_latency: float,
        baseline_latency: float,
        delta_thresholds: dict[str, float] | None,
        max_score_drop: float,
        max_latency_increase_percent: float,
    ) -> RegressionRun:
        metric_deltas: dict[str, float] = {}
        passed = True
        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []

        default_drop_bound = -abs(max_score_drop)

        for metric, c_score in candidate_metrics.items():
            b_score = baseline_metrics.get(metric)
            if b_score is not None:
                delta = round(c_score - b_score, 3)
                metric_deltas[metric] = delta

                # Threshold is maximum acceptable drop (e.g. -0.03)
                threshold = (
                    delta_thresholds.get(metric, default_drop_bound)
                    if delta_thresholds
                    else default_drop_bound
                )
                if threshold > 0:
                    threshold = -threshold

                if delta < threshold:
                    passed = False
                    regressions.append(
                        {
                            "metric": metric,
                            "candidate": c_score,
                            "baseline": b_score,
                            "delta": delta,
                            "threshold": threshold,
                            "status": "REGRESSION",
                        }
                    )
                elif delta > 0.01:
                    improvements.append(
                        {
                            "metric": metric,
                            "candidate": c_score,
                            "baseline": b_score,
                            "delta": delta,
                            "status": "IMPROVEMENT",
                        }
                    )
                else:
                    unchanged.append(
                        {
                            "metric": metric,
                            "candidate": c_score,
                            "baseline": b_score,
                            "delta": delta,
                            "status": "UNCHANGED",
                        }
                    )

        # Latency check
        latency_increase_pct = 0.0
        if baseline_latency > 0:
            latency_increase_pct = round(
                ((candidate_latency - baseline_latency) / baseline_latency) * 100.0, 1
            )
            if latency_increase_pct > max_latency_increase_percent:
                passed = False
                regressions.append(
                    {
                        "metric": "latency",
                        "candidate": candidate_latency,
                        "baseline": baseline_latency,
                        "delta": round(candidate_latency - baseline_latency, 3),
                        "latency_increase_percent": latency_increase_pct,
                        "threshold": max_latency_increase_percent,
                        "status": "REGRESSION",
                    }
                )

        details: dict[str, Any] = {
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "candidate_latency": candidate_latency,
            "baseline_latency": baseline_latency,
            "latency_increase_percent": latency_increase_pct,
            "regressions": regressions,
            "improvements": improvements,
            "unchanged": unchanged,
        }

        return RegressionRun(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            metric_deltas=metric_deltas,
            passed=passed,
            details=details,
        )

    def _calculate_average_metrics(
        self, run: SQLAlchemyEvaluationRun
    ) -> dict[str, float]:
        """
        Averages metric scores from all sample results inside an evaluation run.
        """
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}

        for result in run.results:
            if not result.metrics:
                continue
            for m_name, m_data in result.metrics.items():
                score = m_data.get("score")
                if score is not None:
                    sums[m_name] = sums.get(m_name, 0.0) + float(score)
                    counts[m_name] = counts.get(m_name, 0) + 1

        averages = {}
        for metric, total_sum in sums.items():
            count = counts[metric]
            averages[metric] = round(total_sum / count, 3) if count > 0 else 0.0

        return averages
