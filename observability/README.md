# Fusion RAG — Local Observability Stack & Operational Runbook

This directory contains the operational observability stack for the Fusion RAG platform, providing real-time metric visualization, distributed trace exploration, and reliability monitoring.

---

## 1. Architecture Overview

```
                        ┌─────────────────────────┐
                        │   Fusion RAG Backend    │
                        │        (FastAPI)        │
                        └───────────┬─────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              │                                           │
              ▼                                           ▼
      Prometheus /metrics                            OTLP Traces
              │                                      (gRPC :4317)
              ▼                                           ▼
       ┌──────────────┐                          ┌────────────────┐
       │  Prometheus  │                          │     Jaeger     │
       │   (:9090)    │                          │  (:16686 UI)   │
       └──────┬───────┘                          └────────┬───────┘
              │                                           │
              └─────────────────────┬─────────────────────┘
                                    ▼
                             ┌──────────────┐
                             │   Grafana    │
                             │   (:3000)    │
                             └──────────────┘
```

### Services & Port Mappings

| Service | Port | Purpose | Default Credentials |
|---|---|---|---|
| **Grafana** | `3000` | Operational Dashboards & Metric/Trace Explorer | `admin` / `admin` |
| **Prometheus** | `9090` | Time-Series Metric Storage & Scraper | None (Public read) |
| **Jaeger UI** | `16686` | Distributed Trace Search & Waterfall Inspector | None (Public read) |
| **Jaeger OTLP (gRPC)** | `4317` | OpenTelemetry Trace Ingestion Receiver | N/A |
| **Jaeger OTLP (HTTP)** | `4318` | OpenTelemetry HTTP Ingestion Receiver | N/A |

---

## 2. Quickstart

### Starting the Observability Stack

To launch Prometheus, Jaeger, and Grafana in the background:

```bash
# Option A: Start observability services alongside existing containers
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# Option B: Start standalone observability stack
docker compose -f docker-compose.observability.yml up -d
```

### Stopping the Observability Stack

```bash
docker compose -f docker-compose.observability.yml down
```

To wipe persistent Prometheus/Grafana state:
```bash
docker compose -f docker-compose.observability.yml down -v
```

---

## 3. Pre-Provisioned Grafana Dashboards

Grafana automatically loads both datasources (**Prometheus** & **Jaeger**) and 4 curated dashboards located in `observability/grafana/dashboards/`:

### 1. `Fusion RAG — Retrieval & Pipeline`
- **Purpose**: Answer *"How is my RAG pipeline performing and where is latency originating?"*
- **Key Panels**:
  - **Throughput by Strategy**: Direct, Adaptive, Multi-Agent requests per second.
  - **Pipeline Latency Percentiles**: P50, P95, and P99 end-to-end RAG response times.
  - **Stage Latency (P95)**: Breakdown across `dense`, `sparse`, `fusion`, `mmr`, and `rerank`.
  - **Candidate Funnel**: Number of candidate chunks surviving at each retrieval stage.
  - **Adaptive Replans**: Frequency and classification reasons triggering query expansion/replanning.

### 2. `Fusion RAG — LLM & Providers`
- **Purpose**: Monitor provider latency, streaming responsiveness, and token expenditure.
- **Key Panels**:
  - **Time to First Token (TTFT)**: P50/P95/P99 latency to the initial streaming token (key responsiveness metric).
  - **Total Generation Duration**: P95 duration of completion calls by model (`gemini-1.5-pro`, `gpt-4o-mini`, etc.).
  - **Token Consumption**: Real-time rate of prompt tokens vs. completion tokens.
  - **Circuit Breaker Status**: State of provider circuit breakers (`Closed`, `Half-Open`, `Open`).

### 3. `Fusion RAG — Queue & Workers`
- **Purpose**: Monitor background document ingestion, embedding generation, and worker health.
- **Key Panels**:
  - **Stream Length & Consumer Lag**: Redis Stream depth and pending unacknowledged entries (PEL).
  - **Job Throughput**: Enqueued, completed, retried, and dead-lettered jobs by `task_type`.
  - **Worker Execution Duration**: P95 processing time per job type.
  - **Self-Healing Recoveries**: Orphan auto-claims and `DurableIngestionReaper` recovery counts.

### 4. `Fusion RAG — HTTP & API SLO`
- **Purpose**: High-level service availability, error rates, and API ingress health.
- **Key Panels**:
  - **Request Throughput & Active In-Flight Requests**.
  - **HTTP Error Rate**: 4xx Client vs 5xx Server errors.
  - **Latency Percentiles**: P50, P95, P99 by endpoint route.

---

## 4. Metric → Trace Root Cause Investigation Runbook

When investigating performance degradation or latency spikes, follow this systematic workflow:

```
Grafana Dashboards
       │
       ▼ (Notice P95 Latency Spike on RAG Pipeline)
Identify Stage Bottleneck
       │
       ├─► Dense Search Latency High ──► Inspect Qdrant Collection & Index
       ├─► Sparse Search Latency High ──► Inspect Postgres Full-Text Query / GIN Index
       ├─► Reranking Latency High ──────► Inspect Cross-Encoder / Jina API Latency
       └─► LLM TTFT High ───────────────► Inspect Provider Routing & Model Cold Starts
       │
       ▼
Open Jaeger UI (http://localhost:16686)
       │
       ▼
Search Service: "fusion-rag-backend" | Operation: "rag.chat_orchestration"
       │
       ▼
Inspect Trace Waterfall Hierarchy:
  http.server.request
    └── rag.chat_orchestration
          ├── conversation.prepare_context
          │     └── llm.query_rewrite
          ├── retrieval.dense_search
          ├── retrieval.sparse_search
          ├── retrieval.fusion
          ├── retrieval.mmr_selection
          ├── retrieval.cross_encoder_rerank
          ├── rag.build_prompt
          └── llm.provider.stream (Attribute: llm.ttft_seconds)
       │
       ▼
Extract trace_id to correlate with application structured JSON logs:
  {"timestamp": "...", "trace_id": "<hex>", "span_id": "<hex>", "message": "..."}
```

---

## 5. Async Worker Trace Continuation Runbook

For background document ingestion, traces span across process boundaries via Redis Streams:

1. **Ingress**: `http.server.request` receives upload -> starts `queue.enqueue`.
2. **Propagation**: Producer serializes active W3C `_trace_context` into Redis stream job payload.
3. **Worker Execution**: Worker parses `_trace_context` and creates `queue.consume` with trace continuation:
   ```
   queue.enqueue (Producer Span)
     └── queue.consume (Consumer Span - same Trace ID)
           ├── document.extract_text
           ├── document.chunk_text
           └── embedding.batch_generate
                 └── qdrant.upsert_vectors
   ```

---

## 6. Troubleshooting Checklist

| Problem | Cause | Resolution |
|---|---|---|
| **Prometheus Target DOWN** | Backend not reachable at `backend:8000` or `host.docker.internal:8000` | Ensure backend is running. If running backend directly on host, verify `host.docker.internal:8000/metrics` is reachable. |
| **No Traces in Jaeger** | Backend OTLP exporter not connected or pointing to wrong port | Ensure `OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"` (host) or `"http://jaeger:4317"` (Docker). |
| **Grafana "No Data" on Panels** | No traffic generated yet or PromQL time range too narrow | Send a test query (`POST /api/v1/chat/completions`) and adjust Grafana time window to "Last 15 minutes". |
| **Backend Crashes if Jaeger is Down** | Telemetry fail-safe regression | Telemetry subsystem is isolated with try/except guards and NoOp fallbacks; verify `ENABLE_TELEMETRY=true`. |
