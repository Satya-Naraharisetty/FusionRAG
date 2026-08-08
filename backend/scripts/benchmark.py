import argparse
import asyncio
import os
import sys

# Ensure backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import sessionmaker

from app.api.dependencies import (
    get_chunk_repository,
    get_embedding_generator,
    get_index_cache,
    get_retrieval_service,
    get_vector_store,
)
from app.core.config import settings
from app.db.session import init_postgres_engine
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.reports.report_generator import ReportGenerator
from app.evaluation.runners.benchmark_runner import BenchmarkRunner
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full RAG pipeline benchmark suite."
    )
    parser.add_argument("--dataset", required=True, help="Path to dataset file.")
    parser.add_argument("--dataset-id", default="benchmark-dataset", help="Dataset ID.")
    parser.add_argument("--version", default="1.0.0", help="Dataset version.")
    parser.add_argument(
        "--profile",
        default="quick",
        choices=["quick", "standard", "full", "nightly"],
        help="Evaluation profile.",
    )
    parser.add_argument(
        "--mock", action="store_true", help="Run in mock/stub mode without LLM calls."
    )
    parser.add_argument(
        "--pipelines",
        default="retrieval,generation,agent,conversation",
        help="Comma-separated pipelines.",
    )
    args = parser.parse_args()

    # 1. Establish DB session
    engine = init_postgres_engine(settings.DATABASE_URL)

    # Ensure all evaluation models are created (since they might be missing from alembic migrations)
    from app.evaluation.infrastructure.persistence.models import Base

    Base.metadata.create_all(bind=engine)

    session_local = sessionmaker(bind=engine)
    db = session_local()

    try:
        # 2. Resolve retrieval service and evaluators
        generator = get_embedding_generator()
        vector_store = get_vector_store(request=None)
        chunk_repo = get_chunk_repository(db)
        index_cache = get_index_cache()

        retrieval_service = get_retrieval_service(
            generator=generator,
            vector_store=vector_store,
            chunk_repo=chunk_repo,
            index_cache=index_cache,
        )

        retrieval_eval = RetrievalEvaluator(retrieval_service)
        agent_eval = AgentEvaluator()
        tool_eval = ToolEvaluator()
        conversation_eval = ConversationEvaluator()

        ragas_prov = RagasProvider()
        deepeval_prov = DeepEvalProvider()

        from app.evaluation.runners.evaluation_runner import EvaluationRunner

        eval_runner = EvaluationRunner(
            retrieval_evaluator=retrieval_eval,
            agent_evaluator=agent_eval,
            tool_evaluator=tool_eval,
            conversation_evaluator=conversation_eval,
            ragas_provider=ragas_prov,
            deepeval_provider=deepeval_prov,
        )

        runner = BenchmarkRunner(evaluation_runner=eval_runner)

        # 3. Load dataset
        loader = DatasetLoader()
        dataset = loader.load_dataset(args.dataset, args.dataset_id, args.version)

        pipelines_list = [p.strip() for p in args.pipelines.split(",") if p.strip()]

        print(
            f"Starting benchmark execution for dataset '{dataset.dataset_id}' (v{dataset.version})..."
        )
        run_record = await runner.run_benchmark(
            db=db,
            dataset=dataset,
            profile=args.profile,
            pipelines=pipelines_list,
            mock=args.mock,
        )

        # 4. Generate Reports
        report_gen = ReportGenerator()
        report_paths = report_gen.generate_all_reports(run_record)

        print("\n" + "=" * 50)
        print(f"BENCHMARK COMPLETED: {run_record.status}")
        print("=" * 50)
        print(f"Run ID: {run_record.id}")
        print(f"Total Samples: {run_record.total_samples}")
        print(f"Average Latency: {run_record.avg_latency:.2f}s")
        print(
            f"Total Input/Output Tokens: {run_record.total_input_tokens} / {run_record.total_output_tokens}"
        )
        print(f"Estimated Cost: ${run_record.total_cost:.5f}")
        print(f"Markdown Report Saved to: {report_paths['markdown']}")
        print(f"HTML Report Saved to: {report_paths['html']}")
        print("=" * 50)

    except Exception as e:
        print(f"Benchmark execution crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
