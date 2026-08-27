from app.core.telemetry import (
    AGENT_TASKS_EXECUTED,
    EMBEDDING_CHUNKS,
    HTTP_SERVER_ACTIVE_REQUESTS,
    HTTP_SERVER_DURATION,
    HTTP_SERVER_REQUESTS,
    INGESTION_DOCUMENTS,
    INGESTION_STAGE_DURATION,
    LLM_CIRCUIT_BREAKER_STATE,
    LLM_DURATION,
    LLM_REQUESTS,
    LLM_TIME_TO_FIRST_TOKEN,
    LLM_TOKENS,
    QDRANT_OPERATION_DURATION,
    QUEUE_CONSUMER_LAG,
    QUEUE_JOB_DURATION,
    QUEUE_JOBS,
    QUEUE_ORPHANS_RECOVERED,
    QUEUE_REAPER_RECOVERED,
    QUEUE_STREAM_LENGTH,
    RAG_ADAPTIVE_REPLANS,
    RAG_PIPELINE_DURATION,
    RAG_REQUESTS,
    RETRIEVAL_CANDIDATES_COUNT,
    RETRIEVAL_REQUESTS,
    RETRIEVAL_STAGE_DURATION,
    export_prometheus_metrics,
)


def test_metrics_can_record_without_error():
    # HTTP
    HTTP_SERVER_REQUESTS.labels(method="GET", route="/test", status_code="200").inc()
    HTTP_SERVER_DURATION.labels(method="GET", route="/test", status_code="200").observe(
        0.05
    )
    HTTP_SERVER_ACTIVE_REQUESTS.inc()
    HTTP_SERVER_ACTIVE_REQUESTS.dec()

    # RAG
    RAG_REQUESTS.labels(strategy="baseline", status="success").inc()
    RAG_PIPELINE_DURATION.labels(strategy="baseline", status="success").observe(0.5)
    RAG_ADAPTIVE_REPLANS.labels(reason="low_confidence").inc()
    AGENT_TASKS_EXECUTED.labels(specialist="retrieval", status="success").inc()

    # Retrieval
    RETRIEVAL_REQUESTS.labels(mode="hybrid", status="success").inc()
    RETRIEVAL_STAGE_DURATION.labels(stage="dense").observe(0.02)
    RETRIEVAL_CANDIDATES_COUNT.labels(stage="dense").observe(10)

    # LLM
    LLM_REQUESTS.labels(
        provider="gemini", model="gemini-1.5-pro", status="success"
    ).inc()
    LLM_DURATION.labels(provider="gemini", model="gemini-1.5-pro").observe(1.2)
    LLM_TIME_TO_FIRST_TOKEN.labels(provider="gemini", model="gemini-1.5-pro").observe(
        0.3
    )
    LLM_TOKENS.labels(provider="gemini", model="gemini-1.5-pro", type="prompt").inc(100)
    LLM_CIRCUIT_BREAKER_STATE.labels(provider="gemini", state="closed").set(0)

    # Queue
    QUEUE_STREAM_LENGTH.labels(stream="stream:jobs:document_processing").set(15)
    QUEUE_CONSUMER_LAG.labels(
        stream="stream:jobs:document_processing", group="workers"
    ).set(2)
    QUEUE_JOBS.labels(task_type="PROCESS_DOCUMENT", status="enqueued").inc()
    QUEUE_JOB_DURATION.labels(task_type="PROCESS_DOCUMENT", status="success").observe(
        1.5
    )
    QUEUE_ORPHANS_RECOVERED.labels(task_type="all").inc(1)
    QUEUE_REAPER_RECOVERED.inc(1)

    # Ingestion
    INGESTION_DOCUMENTS.labels(mime_type="application/pdf", status="success").inc()
    INGESTION_STAGE_DURATION.labels(stage="extraction").observe(0.4)
    EMBEDDING_CHUNKS.labels(provider="openai", status="success").inc(5)
    QDRANT_OPERATION_DURATION.labels(operation="search").observe(0.015)

    # Export
    exported = export_prometheus_metrics()
    assert isinstance(exported, bytes)
    text = exported.decode("utf-8")
    assert "http_server_requests_total" in text
    assert "rag_pipeline_duration_seconds" in text
    assert "llm_time_to_first_token_seconds" in text
