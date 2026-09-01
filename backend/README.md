# Fusion RAG — Backend Service

The backend service for the **Fusion RAG Platform**, built with **Python 3.12+**, **FastAPI**, **SQLAlchemy 2.0 (Async + asyncpg)**, **Pydantic v2**, **Qdrant**, and **Redis 7**.

---

## Architecture Overview

The backend is organized into clean domain modules following domain-driven and clean architecture principles:

```
backend/
├── app/
│   ├── api/                     # HTTP REST API routers & Dependency Injection root
│   │   ├── v1/                  # Versioned API routes (auth, chat, documents, admin, health, search, observability, evaluation)
│   │   └── dependencies.py      # Composition root for service and repository injection
│   ├── auth/                    # NIST-compliant authentication, Argon2id, JWT, OAuth, Resend email
│   ├── chat/                    # LLM chat completion, prompt builder, SSE streaming, agent executor, tools
│   ├── core/                    # Global settings, security, rate limiting, queues, cache, reliability, telemetry
│   ├── db/                      # SQLAlchemy session management and base models
│   ├── documents/               # Document ingestion, extractors, chunking, FTS/BM25, Qdrant vector store, reranker
│   ├── evaluation/              # RAG evaluation runners (Ragas, DeepEval), golden datasets, regression suites
│   ├── rag/orchestration/       # Adaptive RAG orchestrator, strategy router, replanner, evidence evaluator
│   └── main.py                  # FastAPI application entrypoint with lifespan startup/shutdown
├── tests/                       # Comprehensive pytest suite (unit, integration, architecture alignment)
└── pyproject.toml               # Python project configuration and dependencies
```

---

## Key Backend Features

1. **Hierarchical Multi-Agent Orchestration**:
   - Master Planner (`MasterAgent`) constructing dynamic dependency DAGs with Kahn's algorithm cycle prevention.
   - **7 Production Specialist Agents**:
     * `ResearchAgent`: 4-stage hybrid Fusion RAG (Qdrant Dense + PostgreSQL Sparse + RRF + MMR + Cross-Encoder).
     * `DocumentAgent`: Targeted chunk/document direct inspection with tenant ownership validation.
     * `AnalysisAgent`: AST-sandboxed symbolic mathematics (`SafeCalculator` + `MathEngine`) and CAGR/growth calculations.
     * `WebSearchAgent`: Real-time internet search with domain relevance gating.
     * `TableAgent`: Structured table extraction, aggregation (`SUM`, `AVG`, `GROWTH`, `MIN`, `MAX`), and upstream DAG consumption.
     * `VisionAgent`: Diagram inspection, OCR transcription, and chart trend reasoning.
     * `GraphAgent`: Multi-hop Knowledge Graph traversal via `PostgresGraphRetriever` and `GraphTraversalService`.
   - Topological wave concurrency ($4.00\times$ measured parallel speedup) with upstream `context.dependency_results` propagation.
   - `ResultEvaluator` with bounded adaptive replanning and Evidence Relevance Gating.
   - `SynthesisAgent` with grounded XML context isolation and Server-Sent Events (SSE) streaming.

2. **Asynchronous Multimodal & Knowledge Graph Ingestion**:
   - Decoupled two-tier architecture: synchronous upload commits fast, while background `DocumentEnrichmentService` executes non-blocking enrichment.
   - Multimodal Element Storage: Markdown/CSV tables and figure/chart elements in `document_elements`.
   - Knowledge Graph Engine: Named entity recognition, normalization, mention linking, relationship triples (`graph_relationships`), and confidence evidence (`relationship_evidence`) with versioned idempotency (`delete_by_version`).

3. **Multi-Branch Hybrid Retrieval**:
   - Dense semantic vector search via **Qdrant** (768-dim embeddings via `jina-embeddings-v3` or `text-embedding-004`).
   - Sparse lexical search via native **PostgreSQL Full-Text Search** (`to_tsvector`/`ts_rank_cd` on GIN indexes) or `InMemoryBM25Index` with class-level pre-tokenization caching.
   - Structured table search via `DocumentElementRepository` and Knowledge Graph traversal via `PostgresGraphRetriever`.
   - Merged with **Reciprocal Rank Fusion (RRF)** ($k=60$) and diversified with **Maximal Marginal Relevance (MMR)** ($\lambda=0.5$).
   - Re-scored with **Jina AI Cross-Encoder REST API** (`jina-reranker-v2-base-multilingual`).

4. **Multi-Format Ingestion**:
   - Parsers for PDF, DOCX, TXT, Markdown, HTML, CSV, and Images (Gemini Vision OCR).
   - Magic-byte file validation, zip-bomb expansion ratio limits (< 100x), and SHA-256 deduplication.
   - Streamed socket malware scanning with ClamAV daemon (fail-closed in production).
   - Durable Redis Streams task queue (`stream:jobs:document_processing`) with consumer groups and auto-claim reapers.

5. **Authentication & Session Security**:
   - Argon2id password hashing, stateless JWT HS256 access tokens (15m expiration), and single-use rotated HTTP-only refresh cookies (7d expiration).
   - OAuth 2.0 social login (Google and GitHub).
   - Resend transactional email verification and passwordless magic link authentication.
   - Account deletion (`DELETE /api/v1/auth/account`) with password re-verification and cascading cleanup.
   - Single admin account invariant managed declaratively via `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

6. **Observability & Evaluation Suite**:
   - OpenTelemetry distributed tracing exported to Jaeger (`:4317` / `:4318`) with automated PII and credential sanitization.
   - Prometheus metrics at `/api/v1/observability/metrics`.
   - RAG evaluation runners (Ragas, DeepEval) benchmarked against golden datasets with regression tracking.

---

## Local Development Setup

### 1. Prerequisites
- Python 3.12+
- [Astral `uv`](https://docs.astral.sh/uv/) package manager
- Running instances of PostgreSQL, Redis, and Qdrant (via `docker compose up -d postgres redis qdrant`)

### 2. Environment Configuration
```bash
cp .env.example .env
```
Ensure `GEMINI_API_KEY`, `JINA_API_KEY`, `JWT_SECRET`, and `ENCRYPTION_MASTER_KEY` are populated.

### 3. Install Dependencies & Start Server
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync --extra dev

# Run database migrations
uv run alembic upgrade head

# Start development server with hot-reloading
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Testing & Quality Assurance

```bash
# Run test suite
pytest

# Run tests with coverage report
pytest --cov=app --cov-report=term-missing

# Lint and format checks
ruff check .
ruff format --check .
```
