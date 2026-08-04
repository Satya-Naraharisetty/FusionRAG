import argparse
import os
import sys
import uuid

# Ensure backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.session import init_postgres_engine
from app.evaluation.infrastructure.persistence.models import SQLAlchemyEvaluationRun
from app.evaluation.runners.regression_runner import RegressionRunner
from sqlalchemy.orm import sessionmaker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run regression check between two evaluation runs.")
    parser.add_argument("--candidate", help="UUID of the candidate run. Defaults to the latest completed run.")
    parser.add_argument("--baseline", help="UUID of the baseline run. Defaults to the second latest completed run.")
    parser.add_argument("--thresholds", help="Custom delta thresholds as key=value comma-separated list (e.g. faithfulness=-0.01).")
    args = parser.parse_args()

    engine = init_postgres_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Resolve runs if not provided
        candidate_id = args.candidate
        baseline_id = args.baseline

        if not candidate_id or not baseline_id:
            print("Resolving evaluation runs automatically from database...")
            completed_runs = db.query(SQLAlchemyEvaluationRun)\
                .filter(SQLAlchemyEvaluationRun.status == "COMPLETED")\
                .order_by(SQLAlchemyEvaluationRun.created_at.desc())\
                .limit(2)\
                .all()

            if len(completed_runs) < 2:
                print("Error: Could not resolve runs. Database must have at least 2 completed runs to perform comparison.")
                sys.exit(1)

            if not candidate_id:
                candidate_id = str(completed_runs[0].id)
            if not baseline_id:
                baseline_id = str(completed_runs[1].id)

        print(f"Comparing Candidate Run `{candidate_id}` with Baseline Run `{baseline_id}`...")

        # Parse custom thresholds
        thresholds_dict = {}
        if args.thresholds:
            for item in args.thresholds.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    thresholds_dict[k.strip()] = float(v.strip())

        # Execute regression check
        runner = RegressionRunner()
        regression_result = runner.compare_runs(
            db=db,
            candidate_run_id=uuid.UUID(candidate_id),
            baseline_run_id=uuid.UUID(baseline_id),
            delta_thresholds=thresholds_dict if thresholds_dict else None
        )

        print("\n" + "=" * 50)
        print("REGRESSION COMPARISON RESULTS")
        print("=" * 50)
        status_text = "🟢 PASSED" if regression_result.passed else "🔴 FAILED (REGRESSION DETECTED)"
        print(f"Status: {status_text}")
        print("-" * 50)
        
        # Display deltas
        for metric, delta in regression_result.metric_deltas.items():
            icon = "▲" if delta > 0.01 else ("▼" if delta < -0.01 else "-")
            print(f"{metric}: {delta:+.3f} {icon}")
        print("=" * 50)

        if not regression_result.passed:
            print("\nRegressions Detected:")
            for reg in regression_result.details.get("regressions", []):
                print(f"  - {reg['metric']}: dropped by {reg['delta']:.3f} (candidate: {reg['candidate']:.3f}, baseline: {reg['baseline']:.3f}), threshold limit was {reg['threshold']:.3f}")
            sys.exit(1)
        else:
            print("\nNo regressions detected. Performance is stable.")
            sys.exit(0)

    except Exception as e:
        print(f"Regression comparison failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
