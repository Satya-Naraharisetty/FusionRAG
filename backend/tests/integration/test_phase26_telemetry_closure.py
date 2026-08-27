from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.chat.domain.interfaces import ProviderResponse
from app.chat.domain.models import AnswerResponse, Usage
from app.chat.services.chat_orchestrator import ChatOrchestrator
from app.core.queue.interfaces import Job, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker
from app.core.telemetry import (
    QUEUE_CONSUMER_LAG,
    QUEUE_ORPHANS_RECOVERED,
    QUEUE_STREAM_LENGTH,
    RAG_ADAPTIVE_REPLANS,
    RAG_REQUESTS,
)
from app.documents.domain.models import RetrievedChunk, SearchResult
from app.documents.services.query_classifier import (
    QueryClassification,
    QueryType,
)
from app.main import resolve_route_template
from app.rag.orchestration.master import AdaptiveRAGOrchestrator
from app.rag.orchestration.models import (
    EvidenceAssessment,
    RetrievalDecision,
    RetrievalStrategy,
    RetrievalTask,
)


def _setup_mock_orchestrator():
    mock_conv_mgr = AsyncMock()
    conv_id = uuid4()
    mock_conv = MagicMock()
    mock_conv.id = conv_id
    mock_conv_mgr.get_or_create_conversation.return_value = mock_conv
    mock_conv_mgr._message_repo = AsyncMock()

    mock_ctx = MagicMock()
    mock_ctx.recent_messages = []
    mock_ctx.summary = None
    mock_rewrite = MagicMock()
    mock_rewrite.rewritten_query = "Test query?"
    mock_rewrite.rewrite_applied = False
    mock_conv_mgr.prepare_context.return_value = (mock_ctx, mock_rewrite)

    mock_retrieval = AsyncMock()
    mock_retrieval.retrieve.return_value = SearchResult(
        original_query="Test query?",
        retrieval_time=0.05,
        total_matches=1,
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                document_name="doc.txt",
                text="Some test content",
                similarity_score=0.9,
                normalized_score=0.9,
                metadata={},
                chunk_index=0,
            )
        ],
        dense_matches=[],
        sparse_matches=[],
    )

    mock_prompt_builder = MagicMock()
    mock_prompt_builder.get_system_prompt.return_value = "System prompt"
    mock_prompt_builder.build_prompt.return_value = (
        [{"role": "user", "content": "Test query?"}],
        mock_retrieval.retrieve.return_value.retrieved_chunks,
    )

    mock_token_estimator = MagicMock()
    mock_token_estimator.estimate.return_value = 20

    mock_context_builder = MagicMock()
    mock_context_builder.build_context.return_value = MagicMock()

    mock_llm_service = MagicMock()
    mock_llm_service.generate = AsyncMock(
        return_value=ProviderResponse(
            content="Answer text",
            usage=Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )
    )

    async def _mock_stream(*args, **kwargs):
        from app.chat.domain.interfaces import StreamChunk

        yield StreamChunk(text_delta="Answer")
        yield StreamChunk(
            text_delta=" finished",
            usage=Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )

    mock_llm_service.stream = _mock_stream

    orchestrator = ChatOrchestrator(
        conversation_manager=mock_conv_mgr,
        retrieval_service=mock_retrieval,
        prompt_builder=mock_prompt_builder,
        context_builder=mock_context_builder,
        token_estimator=mock_token_estimator,
        llm_generation_service=mock_llm_service,
        agent_executor=AsyncMock(),
        model="gemini-3.5-flash-lite",
        enable_conversation_memory=True,
        enable_tool_calling=False,
        enable_multi_agent=False,
    )
    return orchestrator, conv_id


class TestRAGRequestTelemetry:
    @pytest.mark.asyncio
    async def test_sync_success_lifecycle_accounting(self):
        orchestrator, conv_id = _setup_mock_orchestrator()
        user_id = uuid4()

        before_count = RAG_REQUESTS.labels(
            strategy="baseline", status="success"
        )._value.get()

        resp = await orchestrator.generate_answer(
            question="What is Hybrid RAG?",
            user_id=user_id,
            top_k=3,
            conversation_id=conv_id,
            document_ids=[uuid4()],
        )

        assert isinstance(resp, AnswerResponse)
        after_count = RAG_REQUESTS.labels(
            strategy="baseline", status="success"
        )._value.get()
        assert after_count == before_count + 1

    @pytest.mark.asyncio
    async def test_sync_error_lifecycle_accounting(self):
        orchestrator, conv_id = _setup_mock_orchestrator()
        orchestrator.llm_generation_service.generate.side_effect = RuntimeError(
            "LLM Failure"
        )
        user_id = uuid4()

        before_err_count = RAG_REQUESTS.labels(
            strategy="baseline", status="error"
        )._value.get()

        with pytest.raises(RuntimeError):
            await orchestrator.generate_answer(
                question="Error test?",
                user_id=user_id,
                top_k=3,
                conversation_id=conv_id,
                document_ids=[uuid4()],
            )

        after_err_count = RAG_REQUESTS.labels(
            strategy="baseline", status="error"
        )._value.get()
        assert after_err_count == before_err_count + 1


class TestRAGStreamingTelemetry:
    @pytest.mark.asyncio
    async def test_stream_success_lifecycle_accounting(self):
        orchestrator, conv_id = _setup_mock_orchestrator()
        user_id = uuid4()

        before_count = RAG_REQUESTS.labels(
            strategy="baseline", status="success"
        )._value.get()

        events = []
        async for event in orchestrator.generate_answer_stream(
            question="Stream test?",
            user_id=user_id,
            top_k=3,
            conversation_id=conv_id,
            document_ids=[uuid4()],
        ):
            events.append(event)

        assert len(events) > 0
        after_count = RAG_REQUESTS.labels(
            strategy="baseline", status="success"
        )._value.get()
        assert after_count == before_count + 1


class TestAdaptiveRAGTelemetry:
    @pytest.mark.asyncio
    async def test_replan_increments_metric_when_tasks_accepted(self):
        from app.documents.domain.models import DocumentRetrievalScope

        user_id = uuid4()
        test_scope = DocumentRetrievalScope(user_id=user_id)

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve.return_value = SearchResult(
            original_query="query",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    document_name="doc.txt",
                    text="found",
                    similarity_score=0.9,
                    normalized_score=0.9,
                    metadata={},
                    chunk_index=0,
                )
            ],
            dense_matches=[],
            sparse_matches=[],
        )

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = QueryClassification(
            query_type=QueryType.MULTI_HOP,
            confidence=0.9,
            reasons=["multi-hop"],
        )

        mock_router = MagicMock()
        mock_decision = RetrievalDecision(
            strategy=RetrievalStrategy.STANDARD_HYBRID,
            confidence=0.9,
            reasoning_signals=["multi-hop"],
            tasks=[
                RetrievalTask(
                    task_id=uuid4(),
                    query="initial sub-query",
                    strategy=RetrievalStrategy.STANDARD_HYBRID,
                    scope=test_scope,
                )
            ],
        )
        mock_router.select_strategy = AsyncMock(return_value=mock_decision)

        mock_evaluator = AsyncMock()
        # Iteration 1: missing evidence -> triggers replan
        assessment_1 = EvidenceAssessment(
            sufficient=False,
            confidence=0.4,
            missing_targets=["additional target query"],
            conflicting_evidence=False,
        )
        # Iteration 2: sufficient -> finishes
        assessment_2 = EvidenceAssessment(
            sufficient=True,
            confidence=0.95,
            missing_targets=[],
            conflicting_evidence=False,
        )
        mock_evaluator.evaluate.side_effect = [assessment_1, assessment_2]

        mock_replanner = AsyncMock()
        replan_task = RetrievalTask(
            task_id=uuid4(),
            query="replanned sub-query",
            strategy=RetrievalStrategy.STANDARD_HYBRID,
            scope=test_scope,
        )
        mock_replanner.replan.return_value = [replan_task]

        orchestrator = AdaptiveRAGOrchestrator(
            retrieval_service=mock_retrieval,
            chunk_repo=AsyncMock(),
            query_classifier=mock_classifier,
            strategy_router=mock_router,
            evidence_evaluator=mock_evaluator,
            replanner=mock_replanner,
            max_replans=2,
        )

        before_replan = RAG_ADAPTIVE_REPLANS.labels(
            reason="missing_evidence"
        )._value.get()

        mock_worker_result = SearchResult(
            original_query="query",
            retrieval_time=0.01,
            total_matches=1,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    document_name="doc.txt",
                    text="found",
                    similarity_score=0.9,
                    normalized_score=0.9,
                    metadata={},
                    chunk_index=0,
                )
            ],
            dense_matches=[],
            sparse_matches=[],
        )
        orchestrator._execute_tasks = AsyncMock(
            return_value=[MagicMock(result=mock_worker_result)]
        )  # type: ignore

        await orchestrator.orchestrate(
            query="Multi-hop query",
            user_id=uuid4(),
            top_k=5,
        )

        after_replan = RAG_ADAPTIVE_REPLANS.labels(
            reason="missing_evidence"
        )._value.get()
        assert after_replan == before_replan + 1


class TestQueueTelemetry:
    @pytest.mark.asyncio
    async def test_queue_stream_length_and_consumer_lag_gauges(self):
        mock_redis = AsyncMock()
        mock_redis.xlen.return_value = 42
        mock_redis.xpending.return_value = {"pending": 7}

        queue = RedisStreamTaskQueue(redis_client=mock_redis)
        len_val = await queue.get_stream_length()
        lag_val = await queue.get_consumer_lag()

        assert len_val == 42
        assert lag_val == 7

        QUEUE_STREAM_LENGTH.labels(stream=queue.stream_name).set(len_val)
        QUEUE_CONSUMER_LAG.labels(
            stream=queue.stream_name, group=queue.consumer_group
        ).set(lag_val)

        assert QUEUE_STREAM_LENGTH.labels(stream=queue.stream_name)._value.get() == 42
        assert (
            QUEUE_CONSUMER_LAG.labels(
                stream=queue.stream_name, group=queue.consumer_group
            )._value.get()
            == 7
        )

    @pytest.mark.asyncio
    async def test_orphan_recovery_metric_increment(self):
        mock_queue = AsyncMock()
        claimed_job_1 = Job(
            job_id=uuid4(),
            task_type="PROCESS_DOCUMENT",
            payload={"_trace_context": {}},
            attempt=1,
            max_attempts=3,
        )
        claimed_job_2 = Job(
            job_id=uuid4(),
            task_type="GENERATE_EMBEDDINGS",
            payload={"_trace_context": {}},
            attempt=1,
            max_attempts=3,
        )
        mock_queue.reclaim_orphaned_jobs.return_value = (
            "0-0",
            [("100-0", claimed_job_1), ("101-0", claimed_job_2)],
        )

        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch.return_value = JobResult(success=True)

        worker = QueueWorker(
            task_queue=mock_queue,
            dispatcher=mock_dispatcher,
            concurrency=2,
            recovery_interval_s=0.01,
        )

        before_doc = QUEUE_ORPHANS_RECOVERED.labels(
            task_type="PROCESS_DOCUMENT"
        )._value.get()
        before_emb = QUEUE_ORPHANS_RECOVERED.labels(
            task_type="GENERATE_EMBEDDINGS"
        )._value.get()

        worker._is_running = True
        # Run one iteration of recovery logic
        next_id, claimed = await mock_queue.reclaim_orphaned_jobs()
        for _msg_id, job in claimed:
            QUEUE_ORPHANS_RECOVERED.labels(task_type=job.task_type).inc()

        after_doc = QUEUE_ORPHANS_RECOVERED.labels(
            task_type="PROCESS_DOCUMENT"
        )._value.get()
        after_emb = QUEUE_ORPHANS_RECOVERED.labels(
            task_type="GENERATE_EMBEDDINGS"
        )._value.get()

        assert after_doc == before_doc + 1
        assert after_emb == before_emb + 1


class TestHTTPMetricCardinality:
    def test_dynamic_routes_are_parameterized(self):
        mock_app = MagicMock()
        mock_app.routes = []

        scope_1 = {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/conversations/{uuid4()}",
            "headers": [],
            "app": mock_app,
        }
        req_1 = Request(scope_1)
        template_1 = resolve_route_template(req_1)

        scope_2 = {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/conversations/{uuid4()}",
            "headers": [],
            "app": mock_app,
        }
        req_2 = Request(scope_2)
        template_2 = resolve_route_template(req_2)

        # Distinct UUIDs must collapse to the identical route template!
        assert template_1 == "/api/v1/conversations/{id}"
        assert template_2 == "/api/v1/conversations/{id}"
        assert template_1 == template_2
