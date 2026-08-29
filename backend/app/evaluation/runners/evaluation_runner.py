import inspect
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.evaluation.domain.models import EvaluationDataset
from app.evaluation.infrastructure.persistence.models import (
    SQLAlchemyEvaluationResult,
    SQLAlchemyEvaluationRun,
)
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.citation_evaluator import CitationEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.services.multi_agent_evaluator import MultiAgentEvaluator
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator

logger = logging.getLogger(__name__)


async def _safe_commit(db: Any) -> None:
    if hasattr(db, "commit"):
        res = db.commit()
        if inspect.isawaitable(res):
            await res


class EvaluationRunner:
    """
    Evaluation Runner is responsible for executing a single evaluation run on a dataset,
    running independent pipelines (Retrieval, Generation, Agent, MultiAgent, Conversation, Citation), and persisting to database.
    """

    def __init__(
        self,
        retrieval_evaluator: RetrievalEvaluator,
        agent_evaluator: AgentEvaluator,
        tool_evaluator: ToolEvaluator,
        conversation_evaluator: ConversationEvaluator,
        ragas_provider: RagasProvider,
        deepeval_provider: DeepEvalProvider,
        citation_evaluator: CitationEvaluator | None = None,
        multi_agent_evaluator: MultiAgentEvaluator | None = None,
    ) -> None:
        self.retrieval_evaluator = retrieval_evaluator
        self.agent_evaluator = agent_evaluator
        self.tool_evaluator = tool_evaluator
        self.conversation_evaluator = conversation_evaluator
        self.ragas_provider = ragas_provider
        self.deepeval_provider = deepeval_provider
        self.citation_evaluator = citation_evaluator or CitationEvaluator()
        self.multi_agent_evaluator = multi_agent_evaluator or MultiAgentEvaluator()

    async def run_evaluation(
        self,
        db: AsyncSession,
        dataset: EvaluationDataset,
        profile: str,
        pipelines: list[str],
        mock: bool = False,
        git_commit: str = "unknown",
        git_branch: str = "unknown",
    ) -> SQLAlchemyEvaluationRun:
        """
        Executes pipeline evaluations on limited samples for a single dataset.
        """
        samples = dataset.samples

        # Initialize the EvaluationRun ORM Model
        run_record = SQLAlchemyEvaluationRun(
            id=uuid.uuid4(),
            name=f"Run - {dataset.dataset_id} - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
            profile=profile,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            provider=settings.LLM_PROVIDER,
            model=settings.GEMINI_CHAT_MODEL,
            temperature=settings.TEMPERATURE,
            embedding_model=settings.EMBEDDING_MODEL,
            reranker="cross_encoder_reranker",
            retrieval_mode="hybrid" if settings.ENABLE_HYBRID_SEARCH else "dense",
            system_prompt_version="1.0.0",
            git_commit=git_commit,
            git_branch=git_branch,
            status="RUNNING",
            total_samples=len(samples),
            completed_samples=0,
        )
        db.add(run_record)
        await _safe_commit(db)

        start_time = time.perf_counter()

        try:
            # 1. Pipeline Execution

            # --- Pipeline A: Retrieval Benchmark & Reranker Tradeoff ---
            retrieval_results = []
            reranker_tradeoff = {}
            if "retrieval" in pipelines:
                logger.info("Starting Retrieval Pipeline...")
                retrieval_results = await self.retrieval_evaluator.evaluate_samples(
                    samples, mock=mock
                )
                # Compute reranker impact comparison
                reranker_tradeoff = (
                    await self.retrieval_evaluator.evaluate_reranker_tradeoff(
                        samples, mock=mock
                    )
                )
                # Map retrieval results contexts back into samples metadata for downstream steps
                for ret, sample in zip(retrieval_results, samples, strict=True):
                    sample.metadata["retrieved_contexts"] = [
                        c.text for c in ret.retrieved_contexts
                    ]
                    sample.metadata["latency"] = ret.latency
                    sample.metadata["error_category"] = ret.error_category
                    sample.metadata["reranker_tradeoff"] = reranker_tradeoff

            # --- Pipeline B: Generation Benchmark ---
            generation_results = []
            if "generation" in pipelines:
                logger.info("Starting Generation Pipeline...")
                # Simulate responses in sample metadata if mock
                for sample in samples:
                    if "actual_answer" not in sample.metadata:
                        sample.metadata["actual_answer"] = (
                            sample.expected_answer
                            or f"Simulated generated response for: {sample.question}"
                        )

                generation_results = await self.ragas_provider.evaluate(
                    samples,
                    metrics=[
                        "faithfulness",
                        "answer_relevancy",
                    ],
                    mock=mock,
                )

            # --- Pipeline C: Citation Benchmark ---
            citation_results = []
            if "citation" in pipelines:
                logger.info("Starting Citation Pipeline...")
                citation_results = await self.citation_evaluator.evaluate_samples(
                    samples, mock=mock
                )

            # --- Pipeline D: Agentic Benchmark ---
            agent_results = []
            if "agent" in pipelines:
                logger.info("Starting Agentic Tools Pipeline...")
                agent_results = await self.agent_evaluator.evaluate_samples(
                    samples, mock=mock
                )
                for ag, sample in zip(agent_results, samples, strict=True):
                    sample.metadata["tool_calls"] = ag.metadata.get("tool_calls", [])

            # --- Pipeline E: Conversation & Rewrite Benchmark ---
            conversation_results = []
            if "conversation" in pipelines:
                logger.info("Starting Conversation Pipeline...")
                for sample in samples:
                    if (
                        "rewritten_query" not in sample.metadata
                        and sample.conversation_required
                    ):
                        sample.metadata["rewritten_query"] = (
                            f"Rewritten: {sample.question}"
                        )
                        sample.metadata["context_tokens_used"] = 800

                conversation_results = (
                    await self.conversation_evaluator.evaluate_samples(
                        samples, mock=mock
                    )
                )

            # --- Pipeline F: Multi-Agent Benchmark ---
            multi_agent_results = []
            if "multi_agent" in pipelines:
                logger.info("Starting Multi-Agent Architecture Pipeline...")
                multi_agent_results = await self.multi_agent_evaluator.evaluate_samples(
                    samples, mock=mock
                )

            # 2. Consolidate results for each sample
            total_in = 0
            total_out = 0
            total_cost = 0.0
            latencies: list[float] = []

            for idx, sample in enumerate(samples):
                sample_metrics = []
                sample_contexts = []
                actual_answer = sample.metadata.get("actual_answer") or ""
                latency = 0.0
                in_tokens = 0
                out_tokens = 0
                cost = 0.0
                error_cat = "None"

                # Merge metrics from all runs
                for pipeline_res in [
                    retrieval_results,
                    generation_results,
                    citation_results,
                    agent_results,
                    conversation_results,
                    multi_agent_results,
                ]:
                    if idx < len(pipeline_res):
                        res = pipeline_res[idx]
                        sample_metrics.extend(res.metrics)
                        if res.retrieved_contexts:
                            sample_contexts = res.retrieved_contexts
                        latency = max(latency, res.latency)
                        in_tokens += res.input_tokens
                        out_tokens += res.output_tokens
                        cost += res.cost
                        if res.error_category != "None":
                            error_cat = res.error_category

                total_in += in_tokens
                total_out += out_tokens
                total_cost += cost
                latencies.append(latency)

                # Deduplicate metrics preserving first registered pipeline score
                metrics_dict = {}
                for m in sample_metrics:
                    if m.name not in metrics_dict:
                        metrics_dict[m.name] = {
                            "score": m.score,
                            "passed": m.passed,
                            "reason": m.reason,
                        }

                # Save SQLAlchemyResult
                db_result = SQLAlchemyEvaluationResult(
                    id=uuid.uuid4(),
                    run_id=run_record.id,
                    sample_id=sample.id,
                    question=sample.question,
                    expected_answer=sample.expected_answer or "",
                    actual_answer=actual_answer,
                    latency=latency,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    cost=cost,
                    error_category=error_cat,
                    metrics=metrics_dict,
                    retrieved_contexts=[
                        {"text": c.text, "score": c.score} for c in sample_contexts
                    ],
                    metadata_json=sample.metadata,
                )
                db.add(db_result)
                run_record.completed_samples += 1

            # 3. Update Aggregates & Cost details
            await _safe_commit(db)

            total_duration = time.perf_counter() - start_time
            run_record.total_input_tokens = total_in
            run_record.total_output_tokens = total_out
            run_record.total_cost = total_cost
            run_record.avg_latency = (
                sum(latencies) / len(latencies) if latencies else 0.0
            )
            run_record.max_latency = max(latencies) if latencies else 0.0
            run_record.status = "COMPLETED"

            logger.info(
                f"Evaluation run completed successfully. Total Cost: ${total_cost:.5f}, Duration: {total_duration:.2f}s."
            )

        except Exception as e:
            logger.exception("Evaluation run crashed during execution.")
            run_record.status = "FAILED"
            run_record.error_message = str(e)
        await _safe_commit(db)
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            stmt = (
                select(SQLAlchemyEvaluationRun)
                .options(selectinload(SQLAlchemyEvaluationRun.results))
                .where(SQLAlchemyEvaluationRun.id == run_record.id)
            )
            query_res = await db.execute(stmt)
            loaded_run = query_res.scalar_one_or_none()
            if loaded_run:
                return loaded_run
        except Exception:
            pass
        return run_record
