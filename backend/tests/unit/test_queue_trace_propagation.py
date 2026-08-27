from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core.queue.interfaces import Job, JobResult
from app.core.queue.redis_queue import RedisStreamTaskQueue
from app.core.queue.worker import QueueWorker
from app.core.telemetry.propagation import (
    extract_trace_context,
    inject_trace_context,
)


def test_w3c_trace_context_injection_and_extraction():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.tracer")

    with tracer.start_as_current_span("parent.span"):
        carrier = inject_trace_context({})
        assert "traceparent" in carrier
        traceparent = carrier["traceparent"]
        assert traceparent.startswith("00-")

        extracted_ctx = extract_trace_context(carrier)
        assert extracted_ctx is not None


@pytest.mark.asyncio
async def test_redis_queue_enqueue_injects_trace_context():
    from app.core.telemetry import set_tracer_provider_for_test

    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = b"1699999999999-0"

    queue = RedisStreamTaskQueue(redis_client=mock_redis)
    provider = TracerProvider()
    set_tracer_provider_for_test(provider)
    try:
        tracer = provider.get_tracer("test.tracer")
        with tracer.start_as_current_span("parent.request"):
            job = await queue.enqueue(
                task_type="PROCESS_DOCUMENT",
                payload={"doc_id": "test-123"},
            )

        assert "_trace_context" in job.payload
        assert isinstance(job.payload["_trace_context"], dict)
        assert "traceparent" in job.payload["_trace_context"]
    finally:
        set_tracer_provider_for_test(None)


@pytest.mark.asyncio
async def test_worker_handle_message_extracts_trace_context():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    mock_queue = AsyncMock()
    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch.return_value = JobResult(success=True)

    worker = QueueWorker(
        task_queue=mock_queue,
        dispatcher=mock_dispatcher,
        concurrency=1,
    )

    carrier = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
    job = Job(
        job_id=uuid4(),
        task_type="PROCESS_DOCUMENT",
        payload={"_trace_context": carrier, "document_id": "123"},
        attempt=1,
        max_attempts=3,
    )

    res = await worker.handle_message("1000-0", job)
    assert res.success is True
    mock_queue.acknowledge.assert_awaited_once_with("1000-0")
