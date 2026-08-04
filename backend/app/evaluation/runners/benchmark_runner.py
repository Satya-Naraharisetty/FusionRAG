import asyncio
import logging
import os
import subprocess
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.evaluation.domain.models import EvaluationDataset, EvaluationSample
from app.evaluation.infrastructure.persistence.models import (
    SQLAlchemyBenchmarkRun,
    SQLAlchemyEvaluationRun,
)
from app.evaluation.runners.evaluation_runner import EvaluationRunner

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """
    Benchmark Runner coordinates multiple evaluation runs and lifecycle hooks.
    Loads dynamic profiles from benchmark_profiles.yaml manifest.
    """

    def __init__(
        self,
        evaluation_runner: EvaluationRunner
    ) -> None:
        self.evaluation_runner = evaluation_runner

        # Lifecycle hooks
        self._before_hooks: list[Callable[[], Any]] = []
        self._after_hooks: list[Callable[[SQLAlchemyEvaluationRun], Any]] = []

        # Load profiles manifest
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> dict[str, Any]:
        try:
            profile_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "benchmark_profiles.yaml"
            )
            if os.path.exists(profile_path):
                with open(profile_path, encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load benchmark_profiles.yaml manifest: {e}")
        
        # Fallback default configuration if manifest cannot be loaded
        return {
            "quick": {"pipelines": ["retrieval"], "max_samples": 5},
            "standard": {"pipelines": ["retrieval", "generation"], "max_samples": 50},
            "full": {"pipelines": ["retrieval", "generation", "agent", "conversation"], "max_samples": 200},
            "nightly": {"pipelines": ["retrieval", "generation", "agent", "conversation"], "max_samples": 1000}
        }

    def register_before_hook(self, hook: Callable[[], Any]) -> None:
        self._before_hooks.append(hook)

    def register_after_hook(self, hook: Callable[[SQLAlchemyEvaluationRun], Any]) -> None:
        self._after_hooks.append(hook)

    def _get_git_metadata(self) -> tuple[str, str]:
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip()
            return commit, branch
        except Exception:
            return "unknown_commit", "unknown_branch"

    def _apply_profile_limit(self, dataset: EvaluationDataset, profile_cfg: dict[str, Any]) -> list[EvaluationSample]:
        samples = list(dataset.samples)
        max_samples = profile_cfg.get("max_samples", 5)
        return samples[:max_samples]

    async def run_benchmark(
        self,
        db: Session,
        dataset: EvaluationDataset,
        profile: str = "quick",
        pipelines: list[str] = None,
        mock: bool = False
    ) -> SQLAlchemyEvaluationRun:
        """
        Coordinates full benchmark suite runs. Executes hooks, applies profiles,
        and delegates execution to the single-run EvaluationRunner.
        """
        # Resolve profile configuration
        profile_cfg = self.profiles.get(profile, self.profiles["quick"])
        
        # If pipelines are not explicitly passed, read from profile config manifest
        if not pipelines:
            pipelines = profile_cfg.get("pipelines", ["retrieval"])

        # 1. Execute Before Hooks
        logger.info("Executing before-benchmark lifecycle hooks...")
        for hook in self._before_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"Error executing before_benchmark hook: {e}")

        # Limit samples based on profile
        limited_samples = self._apply_profile_limit(dataset, profile_cfg)
        
        # Build dataset with limited samples
        from app.evaluation.domain.models import EvaluationDataset as DomainDataset
        limited_dataset = DomainDataset(
            dataset_id=dataset.dataset_id,
            version=dataset.version,
            hash=dataset.hash,
            sample_count=len(limited_samples),
            description=dataset.description,
            samples=limited_samples
        )

        commit, branch = self._get_git_metadata()

        # Initialize BenchmarkRun tracking record
        benchmark_record = SQLAlchemyBenchmarkRun(
            id=uuid.uuid4(),
            name=f"Benchmark Suite - {profile} - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
            profile=profile,
            status="RUNNING",
            results_summary={},
            metadata_json={"pipelines": pipelines, "dataset_id": dataset.dataset_id, "mock": mock}
        )
        db.add(benchmark_record)
        db.commit()

        # 2. Delegate execution to EvaluationRunner
        run_record = await self.evaluation_runner.run_evaluation(
            db=db,
            dataset=limited_dataset,
            profile=profile,
            pipelines=pipelines,
            mock=mock,
            git_commit=commit,
            git_branch=branch
        )

        # 3. Update Benchmark Run record status
        benchmark_record.status = "COMPLETED" if run_record.status == "COMPLETED" else "FAILED"
        benchmark_record.results_summary = {
            "run_id": str(run_record.id),
            "status": run_record.status,
            "total_samples": run_record.total_samples,
            "completed_samples": run_record.completed_samples,
            "total_cost": run_record.total_cost,
            "avg_latency": run_record.avg_latency
        }
        db.commit()

        # 4. Execute After Hooks
        logger.info("Executing after-benchmark lifecycle hooks...")
        for hook in self._after_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(run_record)
                else:
                    hook(run_record)
            except Exception as e:
                logger.error(f"Error executing after_benchmark hook: {e}")

        db.commit()
        return run_record
