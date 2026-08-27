import logging

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


def _get_or_create_metric(metric_cls, name, documentation, labelnames=(), **kwargs):
    """
    Safely retrieves an existing registered metric from prometheus_client REGISTRY
    or registers a new one, preventing duplicate registration errors across reloads/tests.
    """
    if name in REGISTRY._names_to_collectors:
        collector = REGISTRY._names_to_collectors[name]
        return collector
    try:
        return metric_cls(name, documentation, labelnames=labelnames, **kwargs)
    except ValueError:
        # Fallback if registered under a different collector alias
        return REGISTRY._names_to_collectors.get(name)


# -------------------------------------------------------------
# A. HTTP Server Metrics
# -------------------------------------------------------------
HTTP_SERVER_REQUESTS = _get_or_create_metric(
    Counter,
    "http_server_requests_total",
    "Total HTTP requests received by the server",
    labelnames=["method", "route", "status_code"],
)

HTTP_SERVER_DURATION = _get_or_create_metric(
    Histogram,
    "http_server_duration_seconds",
    "HTTP request processing duration in seconds",
    labelnames=["method", "route", "status_code"],
    buckets=[0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_SERVER_ACTIVE_REQUESTS = _get_or_create_metric(
    Gauge,
    "http_server_active_requests",
    "Current in-flight HTTP requests being processed",
)

# -------------------------------------------------------------
# B. RAG & Agent Metrics
# -------------------------------------------------------------
RAG_REQUESTS = _get_or_create_metric(
    Counter,
    "rag_requests_total",
    "Total RAG generation requests",
    labelnames=["strategy", "status"],
)

RAG_PIPELINE_DURATION = _get_or_create_metric(
    Histogram,
    "rag_pipeline_duration_seconds",
    "Total RAG pipeline execution latency in seconds",
    labelnames=["strategy", "status"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

RAG_ADAPTIVE_REPLANS = _get_or_create_metric(
    Counter,
    "rag_adaptive_replans_total",
    "Total replanning iterations triggered during Adaptive RAG",
    labelnames=["reason"],
)

AGENT_TASKS_EXECUTED = _get_or_create_metric(
    Counter,
    "agent_tasks_executed_total",
    "Total specialist agent task executions",
    labelnames=["specialist", "status"],
)

# -------------------------------------------------------------
# C. Retrieval Metrics
# -------------------------------------------------------------
RETRIEVAL_REQUESTS = _get_or_create_metric(
    Counter,
    "retrieval_requests_total",
    "Total retrieval operations executed",
    labelnames=["mode", "status"],
)

RETRIEVAL_STAGE_DURATION = _get_or_create_metric(
    Histogram,
    "retrieval_stage_duration_seconds",
    "Retrieval duration broken down by stage in seconds",
    labelnames=["stage"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

RETRIEVAL_CANDIDATES_COUNT = _get_or_create_metric(
    Histogram,
    "retrieval_candidates_count",
    "Number of candidates retrieved at each stage",
    labelnames=["stage"],
    buckets=[0, 5, 10, 20, 50, 100, 200],
)

# -------------------------------------------------------------
# D. LLM & Provider Metrics
# -------------------------------------------------------------
LLM_REQUESTS = _get_or_create_metric(
    Counter,
    "llm_requests_total",
    "Total LLM provider invocations",
    labelnames=["provider", "model", "status"],
)

LLM_DURATION = _get_or_create_metric(
    Histogram,
    "llm_duration_seconds",
    "LLM provider generation duration in seconds",
    labelnames=["provider", "model"],
    buckets=[0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

LLM_TIME_TO_FIRST_TOKEN = _get_or_create_metric(
    Histogram,
    "llm_time_to_first_token_seconds",
    "Time to first token (TTFT) for streaming LLM calls in seconds",
    labelnames=["provider", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

LLM_TOKENS = _get_or_create_metric(
    Counter,
    "llm_tokens_total",
    "Total tokens consumed by LLM generation",
    labelnames=["provider", "model", "type"],
)

LLM_CIRCUIT_BREAKER_STATE = _get_or_create_metric(
    Gauge,
    "llm_circuit_breaker_state",
    "Current circuit breaker operational state (0=closed, 1=half_open, 2=open)",
    labelnames=["provider", "state"],
)

# -------------------------------------------------------------
# E. Queue & Worker Metrics
# -------------------------------------------------------------
QUEUE_STREAM_LENGTH = _get_or_create_metric(
    Gauge,
    "queue_stream_length",
    "Total Redis Stream length",
    labelnames=["stream"],
)

QUEUE_CONSUMER_LAG = _get_or_create_metric(
    Gauge,
    "queue_consumer_lag",
    "Pending un-ACKed messages in Redis PEL",
    labelnames=["stream", "group"],
)

QUEUE_JOBS = _get_or_create_metric(
    Counter,
    "queue_jobs_total",
    "Total queue job transitions",
    labelnames=["task_type", "status"],
)

QUEUE_JOB_DURATION = _get_or_create_metric(
    Histogram,
    "queue_job_duration_seconds",
    "Queue job execution duration in seconds",
    labelnames=["task_type", "status"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

QUEUE_ORPHANS_RECOVERED = _get_or_create_metric(
    Counter,
    "queue_orphans_recovered_total",
    "Total orphaned pending jobs claimed via XAUTOCLAIM",
    labelnames=["task_type"],
)

QUEUE_REAPER_RECOVERED = _get_or_create_metric(
    Counter,
    "queue_reaper_recovered_total",
    "Total stale QUEUED documents re-enqueued by DurableIngestionReaper",
)

# -------------------------------------------------------------
# F. Ingestion & Vector Metrics
# -------------------------------------------------------------
INGESTION_DOCUMENTS = _get_or_create_metric(
    Counter,
    "ingestion_documents_total",
    "Total documents processed through ingestion",
    labelnames=["mime_type", "status"],
)

INGESTION_STAGE_DURATION = _get_or_create_metric(
    Histogram,
    "ingestion_stage_duration_seconds",
    "Ingestion pipeline duration per stage in seconds",
    labelnames=["stage"],
    buckets=[0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 15.0],
)

EMBEDDING_CHUNKS = _get_or_create_metric(
    Counter,
    "embedding_chunks_total",
    "Total text chunks vectorized",
    labelnames=["provider", "status"],
)

QDRANT_OPERATION_DURATION = _get_or_create_metric(
    Histogram,
    "qdrant_operation_duration_seconds",
    "Qdrant vector store operation latency in seconds",
    labelnames=["operation"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)


def export_prometheus_metrics() -> bytes:
    """Exports all registered Prometheus metrics in text format."""
    return generate_latest(REGISTRY)
