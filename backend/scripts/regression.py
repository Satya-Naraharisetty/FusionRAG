import argparse
import asyncio
import json
import os
import sys
import uuid

# Ensure backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun
from app.evaluation.runners.regression_runner import RegressionRunner


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run regression check between benchmark runs or against a baseline artifact."
    )
    parser.add_argument(
        "--candidate",
        help="UUID of candidate run in DB.",
    )
    parser.add_argument(
        "--candidate-json",
        help="Path to candidate benchmark JSON report file (e.g. data/evaluation/report_xxx.json).",
    )
    parser.add_argument(
        "--baseline",
        help="UUID of baseline run in DB.",
    )
    parser.add_argument(
        "--baseline-file",
        help="Path to static baseline JSON file (e.g. app/evaluation/baselines/baseline_v1.json).",
    )
    parser.add_argument(
        "--max-score-drop",
        type=float,
        default=0.03,
        help="Maximum allowed drop in quality metrics (default 0.03 = 3%%).",
    )
    parser.add_argument(
        "--max-latency-increase",
        type=float,
        default=20.0,
        help="Maximum allowed percentage increase in latency (default 20.0%%).",
    )
    parser.add_argument(
        "--thresholds",
        help="Custom delta thresholds as key=value comma-separated list (e.g. mrr=-0.02,hit_rate=0.0).",
    )
    parser.add_argument(
        "--ignore-profile-mismatch",
        action="store_true",
        default=False,
        help="Allow comparing candidate and baseline runs that have different profile names.",
    )
    parser.add_argument(
        "--ignore-dataset-mismatch",
        action="store_true",
        default=False,
        help="Allow comparing candidate and baseline runs that have different dataset versions.",
    )
    args = parser.parse_args()

    runner = RegressionRunner()

    # Parse custom thresholds
    thresholds_dict: dict[str, float] = {}
    if args.thresholds:
        for item in args.thresholds.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                thresholds_dict[k.strip()] = float(v.strip())

    # Case A: Comparing directly against a static Baseline JSON file
    if args.baseline_file:
        print(f"Loading baseline artifact from: {args.baseline_file}")
        baseline_data = runner.load_baseline_file(args.baseline_file)

        # Resolve candidate metrics from candidate JSON report or latest DB run
        if args.candidate_json:
            print(f"Loading candidate report from: {args.candidate_json}")
            with open(args.candidate_json, encoding="utf-8") as f:
                cand_data = json.load(f)
            cand_metrics = cand_data.get("metric_averages", {})
            cand_latency = cand_data.get("avg_latency", 0.0)
            cand_dataset_version = cand_data.get("dataset_version", "1.0.0")
            cand_profile = cand_data.get("profile", "fast_deterministic")
        else:
            # Look up latest completed run from DB
            from app.db.session import init_postgres_engine

            try:
                engine = init_postgres_engine(settings.DATABASE_URL or "")
            except Exception:
                engine = create_async_engine(
                    "sqlite+aiosqlite:///:memory:",
                    connect_args={"check_same_thread": False},
                )

            session_local = async_sessionmaker(
                bind=engine, class_=AsyncSession, expire_on_commit=False
            )
            db = session_local()
            try:
                stmt = (
                    select(SQLAlchemyEvaluationRun)
                    .filter(SQLAlchemyEvaluationRun.status == "COMPLETED")
                    .order_by(SQLAlchemyEvaluationRun.created_at.desc())
                    .limit(1)
                )
                res = await db.execute(stmt)
                run = res.scalar_one_or_none()
                if not run:
                    print("Error: No candidate evaluation run found in database.")
                    sys.exit(1)
                cand_metrics = runner._calculate_average_metrics(run)
                cand_latency = run.avg_latency
                cand_dataset_version = run.dataset_version
                cand_profile = run.profile
            finally:
                await db.close()
                await engine.dispose()

        # Run comparison with baseline
        regression_result = runner.compare_with_baseline_data(
            candidate_metrics=cand_metrics,
            candidate_latency=cand_latency,
            baseline=baseline_data,
            candidate_dataset_version=cand_dataset_version,
            candidate_profile=cand_profile,
            delta_thresholds=thresholds_dict if thresholds_dict else None,
            max_score_drop=args.max_score_drop,
            max_latency_increase_percent=args.max_latency_increase,
            ignore_profile_mismatch=args.ignore_profile_mismatch,
            ignore_dataset_mismatch=args.ignore_dataset_mismatch,
        )

    # Case B: Comparing two DB runs
    else:
        from app.db.session import init_postgres_engine

        try:
            engine = init_postgres_engine(settings.DATABASE_URL or "")
        except Exception:
            engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:",
                connect_args={"check_same_thread": False},
            )

        session_local = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        db = session_local()

        try:
            candidate_id = args.candidate
            baseline_id = args.baseline

            if not candidate_id or not baseline_id:
                print("Resolving evaluation runs automatically from database...")
                stmt = (
                    select(SQLAlchemyEvaluationRun)
                    .filter(SQLAlchemyEvaluationRun.status == "COMPLETED")
                    .order_by(SQLAlchemyEvaluationRun.created_at.desc())
                    .limit(2)
                )
                res = await db.execute(stmt)
                completed_runs = list(res.scalars().all())

                if len(completed_runs) < 2:
                    print(
                        "Warning: Database has fewer than 2 completed runs. Skipping DB regression analysis."
                    )
                    sys.exit(0)

                if not candidate_id:
                    candidate_id = str(completed_runs[0].id)
                if not baseline_id:
                    baseline_id = str(completed_runs[1].id)

            print(
                f"Comparing Candidate Run `{candidate_id}` with Baseline Run `{baseline_id}`..."
            )
            regression_result = await runner.compare_runs(
                db=db,
                candidate_run_id=uuid.UUID(candidate_id),
                baseline_run_id=uuid.UUID(baseline_id),
                delta_thresholds=thresholds_dict if thresholds_dict else None,
                max_score_drop=args.max_score_drop,
                max_latency_increase_percent=args.max_latency_increase,
            )
        finally:
            await db.close()
            await engine.dispose()

    # Print regression analysis report
    print("\n" + "=" * 60)
    print("REGRESSION COMPARISON RESULTS")
    print("=" * 60)
    status_text = (
        "[PASSED - NO REGRESSION]"
        if regression_result.passed
        else "[FAILED - QUALITY REGRESSION DETECTED]"
    )
    print(f"Status: {status_text}")
    print("-" * 60)

    details = regression_result.details
    print(
        f"{'Metric':<30} | {'Baseline':>10} | {'Candidate':>10} | {'Delta':>10} | {'Status'}"
    )
    print("-" * 75)

    for metric, delta in regression_result.metric_deltas.items():
        b_val = details.get("baseline_metrics", {}).get(metric, 0.0)
        c_val = details.get("candidate_metrics", {}).get(metric, 0.0)
        m_status = (
            "REGRESSION [-]"
            if delta < -args.max_score_drop
            else ("IMPROVEMENT [+]" if delta > 0.01 else "UNCHANGED [=]")
        )
        print(
            f"{metric:<30} | {b_val:>10.3f} | {c_val:>10.3f} | {delta:>+10.3f} | {m_status}"
        )

    # Latency summary
    b_lat = details.get("baseline_latency", 0.0)
    c_lat = details.get("candidate_latency", 0.0)
    lat_pct = details.get("latency_increase_percent", 0.0)
    lat_status = (
        "REGRESSION [-]" if lat_pct > args.max_latency_increase else "STABLE [=]"
    )
    print(
        f"{'Average Latency (s)':<30} | {b_lat:>10.3f} | {c_lat:>10.3f} | {lat_pct:>+9.1f}% | {lat_status}"
    )

    # List any specific regressions
    regressions = details.get("regressions", [])
    if regressions:
        print("\n" + "=" * 60)
        print("DETECTED REGRESSION DETAILS")
        print("=" * 60)
        for r in regressions:
            if r.get("metric") == "latency":
                print(
                    f"  - Latency increased by +{r.get('latency_increase_percent')}% (Threshold: +{r.get('threshold')}%)"
                )
            else:
                print(
                    f"  - {r.get('metric')}: score dropped by {r.get('delta')} (Allowed drop: {r.get('threshold')})"
                )

    print("=" * 60)

    # Fail loudly with exit code 1 if regression detected for CI gates
    if not regression_result.passed:
        print(
            "\n[FAIL] CI GATE FAILED: Quality regression exceeds configured threshold."
        )
        sys.exit(1)
    else:
        print(
            "\n[SUCCESS] CI GATE PASSED: All metrics meet or exceed baseline standards."
        )
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
