import inspect
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.evaluation.domain.models import RegressionRun
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun

logger = logging.getLogger(__name__)


class RegressionRunner:
    """
    Regression Runner evaluates performance differences between a candidate benchmark run
    and a baseline benchmark run, flagging regressions based on metric thresholds.
    """

    async def compare_runs(
        self,
        db: AsyncSession,
        candidate_run_id: uuid.UUID,
        baseline_run_id: uuid.UUID,
        delta_thresholds: dict[str, float] | None = None,
    ) -> RegressionRun:
        """
        Compare candidate run scores with baseline run scores.
        delta_thresholds defines maximum acceptable drops (e.g., -0.02 means drops worse than -2% fail).
        """
        # Default thresholds (negative represents acceptable drop bounds, e.g., -0.03 means 3% drop allowed)
        # Drops worse than this will trigger failure
        delta_thresholds = delta_thresholds or {
            "faithfulness": -0.02,
            "answer_relevancy": -0.02,
            "recall_at_k": -0.02,
            "precision_at_k": -0.02,
            "hit_rate": 0.0,
            "tool_correctness": 0.0,
            "conversation_quality": -0.05,
        }

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

        # Compute average metrics for both runs
        candidate_averages = self._calculate_average_metrics(candidate)
        baseline_averages = self._calculate_average_metrics(baseline)

        metric_deltas = {}
        passed = True
        details: dict[str, Any] = {
            "candidate_metrics": candidate_averages,
            "baseline_metrics": baseline_averages,
            "regressions": [],
            "improvements": [],
        }

        for metric, c_score in candidate_averages.items():
            b_score = baseline_averages.get(metric)
            if b_score is not None:
                delta = c_score - b_score
                metric_deltas[metric] = round(delta, 3)

                # Check if this delta violates thresholds
                threshold = delta_thresholds.get(metric, -0.05)
                if delta < threshold:
                    passed = False
                    details["regressions"].append(
                        {
                            "metric": metric,
                            "candidate": c_score,
                            "baseline": b_score,
                            "delta": round(delta, 3),
                            "threshold": threshold,
                        }
                    )
                elif delta > 0.02:
                    details["improvements"].append(
                        {
                            "metric": metric,
                            "candidate": c_score,
                            "baseline": b_score,
                            "delta": round(delta, 3),
                        }
                    )

        # Save regression run ORM details if needed or return domain model
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
