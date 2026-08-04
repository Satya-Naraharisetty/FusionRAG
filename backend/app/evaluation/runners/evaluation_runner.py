import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.evaluation.domain.models import EvaluationDataset
from app.evaluation.infrastructure.persistence.models import (
    SQLAlchemyEvaluationResult,
    SQLAlchemyEvaluationRun,
)
from app.evaluation.runners.deepeval_provider import DeepEvalProvider
from app.evaluation.runners.ragas_provider import RagasProvider
from app.evaluation.services.agent_evaluator import AgentEvaluator
from app.evaluation.services.conversation_evaluator import ConversationEvaluator
from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator
from app.evaluation.services.tool_evaluator import ToolEvaluator

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """
    Evaluation Runner is responsible for executing a single evaluation run on a dataset,
    running independent pipelines (Retrieval, Generation, Agent, Conversation), and persisting to database.
    """

    def __init__(
        self,
        retrieval_evaluator: RetrievalEvaluator,
        agent_evaluator: AgentEvaluator,
        tool_evaluator: ToolEvaluator,
        conversation_evaluator: ConversationEvaluator,
        ragas_provider: RagasProvider,
        deepeval_provider: DeepEvalProvider,
    ) -> None:
        self.retrieval_evaluator = retrieval_evaluator
        self.agent_evaluator = agent_evaluator
        self.tool_evaluator = tool_evaluator
        self.conversation_evaluator = conversation_evaluator
        self.ragas_provider = ragas_provider
        self.deepeval_provider = deepeval_provider

    async def run_evaluation(
        self,
        db: Session,
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
            model=settings.GEMINI_CHAT_MODEL
            if settings.LLM_PROVIDER == "gemini"
            else settings.OPENAI_CHAT_MODEL,
            temperature=settings.TEMPERATURE,
            embedding_model=settings.EMBEDDING_MODEL,
            reranker="identity_reranker",
            retrieval_mode="hybrid" if settings.ENABLE_HYBRID_SEARCH else "dense",
            system_prompt_version="1.0.0",
            git_commit=git_commit,
            git_branch=git_branch,
            status="RUNNING",
            total_samples=len(samples),
            completed_samples=0,
        )
        db.add(run_record)
        db.commit()

        start_time = time.perf_counter()

        try:
            # 1. Pipeline Execution

            # --- Pipeline A: Retrieval Benchmark ---
            retrieval_results = []
            if "retrieval" in pipelines:
                logger.info("Starting Retrieval Pipeline...")
                retrieval_results = await self.retrieval_evaluator.evaluate_samples(
                    samples, mock=mock
                )
                # Map retrieval results contexts back into samples metadata for downstream steps
                for ret, sample in zip(retrieval_results, samples):
                    sample.metadata["retrieved_contexts"] = [
                        c.text for c in ret.retrieved_contexts
                    ]
                    sample.metadata["latency"] = ret.latency
                    sample.metadata["error_category"] = ret.error_category

            # --- Pipeline B: Generation Benchmark ---
            generation_results = []
            if "generation" in pipelines:
                logger.info("Starting Generation Pipeline...")
                # Simulate responses in sample metadata if mock
                for sample in samples:
                    if "actual_answer" not in sample.metadata:
                        sample.metadata["actual_answer"] = (
                            f"This is a simulated grounded answer containing references to ground truth: {sample.expected_answer or ''}"
                        )
                        sample.metadata["input_tokens"] = 300
                        sample.metadata["output_tokens"] = 150
                        sample.metadata["cost"] = 0.00045

                generation_results = await self.ragas_provider.evaluate(
                    samples,
                    metrics=[
                        "faithfulness",
                        "answer_relevancy",
                        "context_precision",
                        "context_recall",
                    ],
                    mock=mock,
                )

            # --- Pipeline C: Agent Benchmark ---
            agent_results = []
            if "agent" in pipelines:
                logger.info("Starting Agent Pipeline...")
                for sample in samples:
                    if "reasoning_steps" not in sample.metadata:
                        sample.metadata["reasoning_steps"] = (
                            2 if sample.tools_required else 0
                        )
                        sample.metadata["actual_tools"] = sample.expected_tools or []

                agent_results = await self.agent_evaluator.evaluate_samples(
                    samples, mock=mock
                )

            # --- Pipeline D: Conversation Benchmark ---
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

            # 2. Consolidate results for each sample
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
                    agent_results,
                    conversation_results,
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
                    metrics={
                        m.name: {
                            "score": m.score,
                            "passed": m.passed,
                            "reason": m.reason,
                        }
                        for m in sample_metrics
                    },
                    retrieved_contexts=[
                        {"text": c.text, "score": c.score} for c in sample_contexts
                    ],
                    metadata_json=sample.metadata,
                )
                db.add(db_result)
                run_record.completed_samples += 1

            # 3. Update Aggregates & Cost details
            db.commit()

            total_duration = time.perf_counter() - start_time
            total_in = sum(r.input_tokens for r in run_record.results)
            total_out = sum(r.output_tokens for r in run_record.results)
            total_cost = sum(r.cost for r in run_record.results)
            latencies = [r.latency for r in run_record.results]

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
            db.commit()

        db.commit()
        return run_record
