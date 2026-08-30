import inspect
import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import (
    check_rate_limit,
    get_benchmark_runner,
    get_current_user_context,
    get_db,
)
from app.core.config import settings
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.infrastructure.persistence.models import (
    SQLAlchemyEvaluationRun,
)
from app.evaluation.reports.report_generator import ReportGenerator
from app.evaluation.runners.benchmark_runner import BenchmarkRunner
from app.evaluation.runners.regression_runner import RegressionRunner

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


def check_admin_user(
    user_context: dict[str, Any] = Depends(get_current_user_context),
) -> dict[str, Any]:
    """
    Dependency to restrict evaluation endpoints to admin users.
    """
    if user_context.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required to execute evaluations.",
        )
    return user_context


# Lazy import/wire helper dependencies that will be registered in dependencies.py
def get_dataset_loader() -> DatasetLoader:
    return DatasetLoader()


def get_regression_runner() -> RegressionRunner:
    return RegressionRunner()


def get_report_generator() -> ReportGenerator:
    return ReportGenerator(output_dir=settings.EVALUATION_RESULTS_DIR)


# We will fetch BenchmarkRunner directly from dependencies.py DI


class BenchmarkRequest(Any):
    pass


class RunBenchmarkRequest(BaseModel):
    dataset_path: str = Field(
        ..., description="Absolute or relative path to the dataset file."
    )
    dataset_id: str = Field(..., description="Unique dataset identifier.")
    version: str = Field("1.0.0", description="Dataset version.")
    profile: str = Field(
        "quick", description="Evaluation profile: quick, standard, full, nightly."
    )
    pipelines: list[str] | None = Field(
        default=None,
        description="Pipelines to execute: retrieval, generation, agent, conversation.",
    )
    mock: bool = Field(
        False,
        description="Whether to simulate metrics outputs without external model execution.",
    )


class RegressionRequest(BaseModel):
    candidate_run_id: UUID = Field(
        ..., description="ID of the candidate evaluation run."
    )
    baseline_run_id: UUID = Field(..., description="ID of the baseline evaluation run.")
    thresholds: dict[str, float] | None = Field(
        default=None, description="Custom regression thresholds."
    )


@router.post(
    "/benchmark",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(check_rate_limit)],
)
async def start_benchmark(
    req: RunBenchmarkRequest,
    db: AsyncSession = Depends(get_db),
    loader: DatasetLoader = Depends(get_dataset_loader),
    runner: BenchmarkRunner = Depends(get_benchmark_runner),
    report_gen: ReportGenerator = Depends(get_report_generator),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> dict[str, Any]:
    """
    Trigger an offline pipeline benchmark execution.
    Runs asynchronously if needed, or synchronously for small runs.
    """
    try:
        # Load dataset
        dataset = loader.load_dataset(
            file_path=req.dataset_path, dataset_id=req.dataset_id, version=req.version
        )

        # Validate dataset
        if not loader.validate_dataset(dataset):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset validation failed: missing ID or question fields.",
            )

        # Run benchmark
        run_record = await runner.run_benchmark(
            db=db,
            dataset=dataset,
            profile=req.profile,
            pipelines=req.pipelines,
            mock=req.mock,
        )

        # Generate files reports
        report_gen.generate_all_reports(run_record)

        return {
            "message": "Benchmark run finished successfully.",
            "run_id": str(run_record.id),
            "status": run_record.status,
            "total_samples": run_record.total_samples,
            "total_cost": run_record.total_cost,
            "avg_latency": run_record.avg_latency,
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Benchmark execution failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Benchmark execution failed due to an internal error.",
        )


@router.post(
    "/regression",
    response_model=None,
    dependencies=[Depends(check_rate_limit)],
)
async def run_regression_check(
    req: RegressionRequest,
    db: AsyncSession = Depends(get_db),
    runner: RegressionRunner = Depends(get_regression_runner),
    report_gen: ReportGenerator = Depends(get_report_generator),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> dict[str, Any]:
    """
    Compare two runs in the database to detect regressions.
    """
    try:
        regression_result = await runner.compare_runs(
            db=db,
            candidate_run_id=req.candidate_run_id,
            baseline_run_id=req.baseline_run_id,
            delta_thresholds=req.thresholds,
        )

        # Optionally regenerate candidate reports to embed the regression comparison details
        stmt = (
            select(SQLAlchemyEvaluationRun)
            .options(selectinload(SQLAlchemyEvaluationRun.results))
            .where(SQLAlchemyEvaluationRun.id == req.candidate_run_id)
        )
        candidate_res: Any = db.execute(stmt)
        if inspect.isawaitable(candidate_res):
            candidate_res = await candidate_res
        candidate_run = candidate_res.scalar_one_or_none()
        if candidate_run:
            report_gen.generate_all_reports(candidate_run, regression_result)

        return {
            "passed": regression_result.passed,
            "baseline_run_id": str(regression_result.baseline_run_id),
            "candidate_run_id": str(regression_result.candidate_run_id),
            "metric_deltas": regression_result.metric_deltas,
            "details": regression_result.details,
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Regression analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Regression analysis failed due to an internal error.",
        )


@router.get("/runs", response_model=None)
async def list_evaluation_runs(
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> list[dict[str, Any]]:
    """
    Retrieve all historical evaluation runs from database.
    """
    stmt = select(SQLAlchemyEvaluationRun).order_by(
        SQLAlchemyEvaluationRun.created_at.desc()
    )
    runs_res: Any = db.execute(stmt)
    if inspect.isawaitable(runs_res):
        runs_res = await runs_res
    runs = list(runs_res.scalars().all())
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "profile": r.profile,
            "dataset_id": r.dataset_id,
            "dataset_version": r.dataset_version,
            "status": r.status,
            "total_samples": r.total_samples,
            "completed_samples": r.completed_samples,
            "total_cost": r.total_cost,
            "avg_latency": r.avg_latency,
            "created_at": r.created_at,
        }
        for r in runs
    ]


@router.get("/reports/{run_id}", response_model=None)
async def get_evaluation_report(
    run_id: UUID,
    format: str = "markdown",
    db: AsyncSession = Depends(get_db),
    report_gen: ReportGenerator = Depends(get_report_generator),
    _admin: dict[str, Any] = Depends(check_admin_user),
) -> FileResponse:
    """
    Retrieve generated Markdown, JSON, HTML, or CSV report files for a run.
    If the file is missing from disk, regenerates it on-demand from the database record.
    """
    ext = "md"
    content_type = "text/markdown"

    if format == "json":
        ext = "json"
        content_type = "application/json"
    elif format == "csv":
        ext = "csv"
        content_type = "text/csv"
    elif format == "html":
        ext = "html"
        content_type = "text/html"

    report_path = os.path.join(
        settings.EVALUATION_RESULTS_DIR, f"report_{run_id}.{ext}"
    )

    if not os.path.exists(report_path):
        # Attempt on-demand regeneration from DB run record
        stmt = (
            select(SQLAlchemyEvaluationRun)
            .options(selectinload(SQLAlchemyEvaluationRun.results))
            .where(SQLAlchemyEvaluationRun.id == run_id)
        )
        res = await db.execute(stmt)
        run_record = res.scalar_one_or_none()

        if not run_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report file not found for run {run_id} in {format} format.",
            )

        report_gen.generate_all_reports(run_record)

    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report file not found for run {run_id} in {format} format.",
        )

    return FileResponse(
        path=report_path,
        media_type=content_type,
        filename=os.path.basename(report_path),
    )
