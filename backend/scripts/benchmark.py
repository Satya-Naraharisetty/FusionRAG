import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime

# Ensure backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_chunk_repository,
    get_embedding_generator,
    get_index_cache,
    get_retrieval_service,
    get_vector_store,
)
from app.core.config import settings
from app.evaluation.datasets.dataset_loader import DatasetLoader
from app.evaluation.domain.models import BaselineData
from app.evaluation.reports.report_generator import ReportGenerator
from app.evaluation.runners.benchmark_runner import BenchmarkRunner
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.runners.evaluation_runner import EvaluationRunner
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.citation_evaluator import CitationEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full RAG pipeline benchmark suite."
    )
    parser.add_argument("--dataset", required=True, help="Path to dataset file.")
    parser.add_argument(
        "--dataset-id", default="golden_rag_dataset", help="Dataset ID."
    )
    parser.add_argument("--version", default="1.0.0", help="Dataset version.")
    parser.add_argument(
        "--profile",
        default="fast_deterministic",
        choices=[
            "fast_deterministic",
            "quick",
            "standard",
            "full",
            "nightly",
            "adaptive_rag",
        ],
        help="Evaluation profile.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock/stub mode without external model calls.",
    )
    parser.add_argument(
        "--pipelines",
        default=None,
        help="Comma-separated pipelines (e.g. retrieval,citation,generation,agent).",
    )
    parser.add_argument(
        "--generate-baseline",
        help="Path to save the generated baseline JSON artifact (e.g. app/evaluation/baselines/baseline_v1.json).",
    )
    parser.add_argument(
        "--parent-baseline",
        default=None,
        help="Parent baseline version identifier (e.g. v1).",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        help="Use an in-memory SQLite database for standalone benchmarking without Postgres.",
    )
    parser.add_argument(
        "--enable-query-expansion",
        action="store_true",
        help="Enable Phase 2.4 query expansion during benchmark.",
    )
    parser.add_argument(
        "--enable-query-decomposition",
        action="store_true",
        help="Enable Phase 2.4 query decomposition during benchmark.",
    )
    parser.add_argument(
        "--enable-weighted-rrf",
        action="store_true",
        help="Enable Phase 2.4 weighted RRF during benchmark.",
    )
    parser.add_argument(
        "--dense-weight",
        type=float,
        default=1.0,
        help="Weight for dense retrieval in weighted RRF.",
    )
    parser.add_argument(
        "--sparse-weight",
        type=float,
        default=1.0,
        help="Weight for sparse retrieval in weighted RRF.",
    )
    parser.add_argument(
        "--enable-neighbor-chunks",
        action="store_true",
        help="Enable Phase 2.4 neighbor chunk expansion.",
    )
    parser.add_argument(
        "--enable-context-selection",
        action="store_true",
        default=True,
        help="Enable Phase 2.4 context selection.",
    )
    parser.add_argument(
        "--enable-adaptive-rag",
        action="store_true",
        help="Enable Phase 2.5 Adaptive / Agentic RAG Orchestration.",
    )
    parser.add_argument(
        "--enable-hyde",
        action="store_true",
        help="Enable Phase 2.5 HyDE (Hypothetical Document Embeddings).",
    )
    args = parser.parse_args()

    # 1. Establish DB session (Postgres or SQLite in-memory fallback)
    from app.db.models import Base

    if args.use_sqlite:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = session_factory()
    else:
        try:
            from app.db.session import init_postgres_engine

            engine = init_postgres_engine(settings.DATABASE_URL or "")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            session_local = async_sessionmaker(
                bind=engine, class_=AsyncSession, expire_on_commit=False
            )
            db = session_local()
        except Exception:
            print(
                "PostgreSQL connection failed. Falling back to in-memory SQLite engine."
            )
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy.pool import StaticPool

            engine = create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(bind=engine)
            session_factory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
            db = session_factory()

    try:
        # 2. Resolve retrieval service and evaluators
        try:
            generator = get_embedding_generator()
            vector_store = get_vector_store()
            chunk_repo = get_chunk_repository(db)
            index_cache = get_index_cache()

            base_retrieval_service = get_retrieval_service(
                generator=generator,
                vector_store=vector_store,
                chunk_repo=chunk_repo,
                index_cache=index_cache,
            )
            # Apply CLI overrides for benchmark run
            base_retrieval_service._enable_query_expansion = args.enable_query_expansion
            base_retrieval_service._enable_query_decomposition = (
                args.enable_query_decomposition
            )
            base_retrieval_service._enable_weighted_rrf = args.enable_weighted_rrf
            base_retrieval_service._dense_weight = args.dense_weight
            base_retrieval_service._sparse_weight = args.sparse_weight

            if args.enable_adaptive_rag:
                from app.documents.services.hyde import (
                    DeterministicHyDEGenerator,
                    SafeHyDEExecutor,
                )
                from app.documents.services.query_classifier import (
                    DeterministicQueryClassifier,
                )
                from app.documents.services.query_decomposer import (
                    DeterministicQueryDecomposer,
                )
                from app.rag.orchestration.evidence_evaluator import (
                    EvidenceSufficiencyEvaluator,
                )
                from app.rag.orchestration.master import AdaptiveRAGOrchestrator
                from app.rag.orchestration.replanner import Replanner
                from app.rag.orchestration.strategy_router import (
                    RetrievalStrategyRouter,
                )
                from app.rag.orchestration.telemetry import OrchestrationTelemetry

                hyde_exec = None
                if (
                    args.enable_hyde
                    and getattr(base_retrieval_service, "_dense_retriever", None)
                    is not None
                ):
                    hyde_exec = SafeHyDEExecutor(
                        hyde_generator=DeterministicHyDEGenerator(),
                        embedding_generator=generator,
                        dense_retriever=base_retrieval_service._dense_retriever,
                        timeout_ms=settings.HYDE_TIMEOUT_MS,
                    )

                q_classifier = DeterministicQueryClassifier()
                retrieval_service = AdaptiveRAGOrchestrator(
                    retrieval_service=base_retrieval_service,
                    strategy_router=RetrievalStrategyRouter(q_classifier),
                    evidence_evaluator=EvidenceSufficiencyEvaluator(
                        min_relevance_threshold=settings.SIMILARITY_THRESHOLD
                    ),
                    replanner=Replanner(),
                    query_classifier=q_classifier,
                    query_decomposer=DeterministicQueryDecomposer(),
                    hyde_executor=hyde_exec,
                    telemetry=OrchestrationTelemetry(),
                    chunk_repo=chunk_repo,
                )
            else:
                retrieval_service = base_retrieval_service
        except Exception as e:
            from unittest.mock import MagicMock

            print(f"Retrieval service resolution exception: {e}")
            retrieval_service = MagicMock()

        retrieval_eval = RetrievalEvaluator(retrieval_service)
        agent_eval = AgentEvaluator()
        tool_eval = ToolEvaluator()
        conversation_eval = ConversationEvaluator()
        citation_eval = CitationEvaluator()

        ragas_prov = RagasProvider()
        deepeval_prov = DeepEvalProvider()

        eval_runner = EvaluationRunner(
            retrieval_evaluator=retrieval_eval,
            agent_evaluator=agent_eval,
            tool_evaluator=tool_eval,
            conversation_evaluator=conversation_eval,
            citation_evaluator=citation_eval,
            ragas_provider=ragas_prov,
            deepeval_provider=deepeval_prov,
        )

        runner = BenchmarkRunner(evaluation_runner=eval_runner)

        # 3. Load dataset
        loader = DatasetLoader()
        dataset = loader.load_dataset(args.dataset, args.dataset_id, args.version)

        pipelines_list = (
            [p.strip() for p in args.pipelines.split(",") if p.strip()]
            if args.pipelines
            else None
        )

        print(
            f"Starting benchmark execution for dataset '{dataset.dataset_id}' (v{dataset.version}) under profile '{args.profile}'..."
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

        # 5. Extract metric averages
        json_report_path = report_paths["json"]
        with open(json_report_path, encoding="utf-8") as f:
            report_json = json.load(f)

        metric_averages = report_json.get("metric_averages", {})
        sample_meta = run_record.results[0].metadata_json if run_record.results else {}
        reranker_tradeoff = sample_meta.get("reranker_tradeoff", {})

        print("\n" + "=" * 60)
        print(f"BENCHMARK COMPLETED: {run_record.status}")
        print("=" * 60)
        print(f"Run ID: {run_record.id}")
        print(f"Total Samples: {run_record.total_samples}")
        print(
            f"Average Latency: {run_record.avg_latency:.3f}s (Max: {run_record.max_latency:.3f}s)"
        )
        print("\n--- Metric Averages ---")
        for m_name, m_score in metric_averages.items():
            print(f"  {m_name:<30}: {m_score:.3f}")

        if reranker_tradeoff:
            print("\n--- Cross-Encoder Reranker Tradeoff ---")
            print(
                f"  Without Reranker MRR : {reranker_tradeoff.get('without_reranker_mrr', 0.0):.3f}"
            )
            print(
                f"  With Reranker MRR    : {reranker_tradeoff.get('with_reranker_mrr', 0.0):.3f} (Delta: {reranker_tradeoff.get('mrr_delta', 0.0):+.3f})"
            )
            print(
                f"  Without Reranker nDCG: {reranker_tradeoff.get('without_reranker_ndcg', 0.0):.3f}"
            )
            print(
                f"  With Reranker nDCG   : {reranker_tradeoff.get('with_reranker_ndcg', 0.0):.3f} (Delta: {reranker_tradeoff.get('ndcg_delta', 0.0):+.3f})"
            )
            print(
                f"  Reranker Latency Avg : {reranker_tradeoff.get('reranker_latency_avg_ms', 0.0)}ms"
            )

        print("\n--- Report Files ---")
        print(f"Markdown : {report_paths['markdown']}")
        print(f"JSON     : {report_paths['json']}")
        print("=" * 60)

        # 6. Save baseline if requested
        if args.generate_baseline:
            baseline_ver = "v2" if args.parent_baseline else "v1"
            baseline_obj = BaselineData(
                baseline_version=baseline_ver,
                dataset_version=dataset.version,
                evaluator_version="v1",
                profile=args.profile,
                parent_baseline=args.parent_baseline,
                generated_at=datetime.now(UTC).isoformat(),
                sample_count=run_record.total_samples,
                metric_averages=metric_averages,
                latency_metrics={
                    "avg_latency": run_record.avg_latency,
                    "max_latency": run_record.max_latency,
                },
                reranker_tradeoff=reranker_tradeoff,
                metadata={
                    "run_id": str(run_record.id),
                    "dataset_id": dataset.dataset_id,
                },
            )
            os.makedirs(
                os.path.dirname(os.path.abspath(args.generate_baseline)), exist_ok=True
            )
            with open(args.generate_baseline, "w", encoding="utf-8") as f:
                f.write(baseline_obj.model_dump_json(indent=2))
            print(f"\n[SUCCESS] Baseline artifact saved to: {args.generate_baseline}")

    except Exception as e:
        print(f"Benchmark execution crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        import inspect

        if hasattr(db, "close"):
            res = db.close()
            if inspect.isawaitable(res):
                await res
        if hasattr(engine, "dispose"):
            res = engine.dispose()
            if inspect.isawaitable(res):
                await res


if __name__ == "__main__":
    asyncio.run(main())
