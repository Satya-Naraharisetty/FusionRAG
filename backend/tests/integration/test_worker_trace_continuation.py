from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core.queue.interfaces import JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker
from app.core.telemetry import set_tracer_provider_for_test


@pytest.mark.asyncio
async def test_worker_trace_continuation_e2e():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider_for_test(provider)

    try:
        mock_redis = AsyncMock()
        mock_redis.xadd.return_value = b"1699999999999-0"

        queue = RedisStreamTaskQueue(redis_client=mock_redis)

        # 1. Enqueue inside an active producer span
        tracer = provider.get_tracer("test.producer")
        with tracer.start_as_current_span("http.producer.span") as root_span:
            job = await queue.enqueue(
                task_type="PROCESS_DOCUMENT",
                payload={"document_id": str(uuid4())},
            )
            producer_trace_id = trace.format_trace_id(
                root_span.get_span_context().trace_id
            )

        # 2. Worker consumes and executes inside that context
        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch.return_value = JobResult(success=True)

        worker = QueueWorker(
            task_queue=queue,
            dispatcher=mock_dispatcher,
            concurrency=1,
        )

        await worker.handle_message("1000-0", job)

        spans = exporter.get_finished_spans()
        span_names = [s.name for s in spans]

        assert "queue.enqueue" in span_names
        assert "queue.consume" in span_names
        assert "http.producer.span" in span_names

        consume_span = next(s for s in spans if s.name == "queue.consume")
        consume_trace_id = trace.format_trace_id(
            consume_span.get_span_context().trace_id
        )
        assert consume_trace_id == producer_trace_id
    finally:
        set_tracer_provider_for_test(None)
