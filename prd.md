# Product Requirements Document (PRD): Production-Grade Fusion RAG Chatbot

## 1. Executive Summary

This document specifies the complete, as-built product requirements for the **Fusion RAG Chatbot** — a production-grade, enterprise-class Retrieval-Augmented Generation platform built as a definitive reference implementation of modern AI engineering.

The system is fully deployed, containerized, and observable. It delivers highly accurate, grounded, citation-backed answers from user-uploaded documents, implemented across four iterative phases:
- **Phase 1**: Core auth, two-tier document ingestion, and basic hybrid RAG
- **Phase 2**: History-aware retrieval, conversation memory, adaptive RAG, and agentic tool calling
- **Phase 3**: Hierarchical multi-agent architecture with four specialist agents
- **Phase 4**: Full observability suite, automated quality evaluation, and production hardening

---

## 2. Vision

To build the definitive production reference implementation of a Fusion RAG Chatbot, demonstrating concretely how to transition RAG from a fragile prototype to a robust, observable, resilient, enterprise-grade AI platform that any engineer can study, fork, and deploy.

---

## 3. Objectives

1. **Technical Excellence**: Implement industry-standard best practices across hybrid retrieval, query rewriting, reranking, conversation memory, agentic orchestration, and streaming generation.
2. **Fast Onboarding**: Enable any engineer to clone the repository and run the full stack via `docker compose up` within minutes.
3. **High Groundedness**: Minimize hallucination via strictly grounded generation, inline citation references, XML prompt isolation, and prompt injection defenses.
4. **Total Observability**: Expose the entire RAG decision chain in the UI, Prometheus, and Jaeger — routing decisions, retrieval scores, replanning events, token accounting, latency breakdowns.
5. **Resilient Multi-Strategy Retrieval**: Automatically adapt between Direct Retrieval, HyDE, Multi-Hop Decomposition, and Multi-Agent execution based on query complexity.
6. **Production Security**: NIST SP 800-63B auth, Argon2id, JWT rotation, OAuth 2.0, ClamAV, magic-byte validation, fail-fast production config guards.

---

## 4. Product Scope (As Built Across All Phases)

### Phase 1 - Foundation: Auth, Ingestion & Basic RAG

#### Authentication & Session Security
- Email/password registration with **Argon2id** password hashing
- **JWT HS256** access tokens (15-minute expiry) and single-use rotated **HTTP-only refresh cookies** (7-day)
- Refresh token replay attack detection: reuse of a revoked token immediately revokes **all** user sessions
- **OAuth 2.0** social login via Google and GitHub (state-verified authorization code flow)
- **Transactional email** verification and magic-link login powered by Resend API
- **Rate limiting**: sliding-window Redis-backed with in-memory fallback; login brute-force lockout (5 attempts per 5-minute window)
- **Single admin invariant**: ADMIN_EMAIL env var promotes exactly one account to `admin` role at startup
- **Account deletion**: password-gated DELETE /api/v1/auth/account with cascade cleanup, 10/min rate limit
- **Per-user encryption keys**: Data Encryption Keys (DEK) wrapped by ENCRYPTION_MASTER_KEY in `user_encryption_keys`

#### Two-Tier Document Management
- **Library Documents** (scope=LIBRARY): uploaded to /api/v1/documents/upload, shared across all conversations
- **Conversation Attachments** (scope=CONVERSATION): uploaded in the chat composer with conversation_id param, cascade-deleted when conversation is deleted
- **Supported formats**: PDF, DOCX, TXT, Markdown (.md), HTML, CSV, Images (PNG/JPG/JPEG/WEBP via Gemini Vision OCR)
- **File validation**: magic-byte signature checking, zip-bomb ratio guard (< 100x), 25 MB size limit
- **Malware defense**: streaming ClamAV socket scan (clamd TCP port 3310), MALWARE_SCAN_FAIL_CLOSED=True
- **Deduplication**: SHA-256 content checksum; duplicate uploads per user return the existing document record
- **Storage**: PostgreSQL binary BLOB (document_files table) or local filesystem (UPLOAD_DIR)
- **Async ingestion queue**: Redis Streams with consumer groups, ACK acknowledgment, dead-letter routing, and exponential backoff retries (base: 2s, max: 60s)

#### Text Processing & Chunking
- `TextCleaner`: whitespace normalization, unicode sanitization, line-break repair, boilerplate stripping
- `MetadataExtractor`: automated title, author, date, language (langdetect), word count, and tags extraction
- **Chunking strategies**:
  - `recursive` (default): splits on paragraph/line/word/char boundaries, CHUNK_SIZE=500, CHUNK_OVERLAP=50
  - `semantic`: splits on embedding cosine similarity shifts between sentences
  - `parent_child`: indexes small child chunks (400 chars) for retrieval, expands to parent (1500 chars) at context time
  - `sentence_window`: indexes single sentences, expands +/- SENTENCE_WINDOW_SIZE=2 at context time
  - `contextual`: prepends per-chunk document context summary before embedding
- Chunks stored in `document_chunks` with generated TSVECTOR GIN-indexed `search_vector` column
- Embedding status tracked in `document_embeddings` (provider, model, dimension, version, status)

#### Hybrid Retrieval Engine
- **Dense search**: Qdrant HNSW, jina-embeddings-v3 (768-dim Matryoshka), retrieval.query task flag, user_id payload filter
- **Sparse search**: PostgreSQL FTS (websearch_to_tsquery + ts_rank_cd + GIN index) or in-memory BM25 with shared tokenization cache
- **RRF**: 1 / (rank + k) formula, RRF_K=60, optional DENSE_WEIGHT / SPARSE_WEIGHT
- **MMR**: diversity selection, MMR_LAMBDA=0.5
- **Cross-Encoder reranking**: Jina AI REST API (jina-reranker-v2-base-multilingual), RERANK_TOP_K=5, asyncio.Semaphore(4), graceful fallback to MMR order on failure
- **Context selector**: CONTEXT_MAX_TOKENS=6000, CONTEXT_MAX_CHUNKS=12, minimum score threshold, neighbor/parent expansion

---

### Phase 2 - Adaptive RAG, Conversation Memory & Agentic Tools

#### History-Aware Retrieval
- `LLMHistoryRewriter`: pronoun/follow-up heuristic detection; calls Gemini to rewrite context-dependent follow-up questions into standalone search queries using last 6 messages
- Redis cache key: rewrite:{conversation_id}:{last_message_id}:{sha256_query}, TTL 2 hours
- `@documents` mention: detects and strips control directive, activates documents-priority mode in PromptBuilder
- **Document context stickiness**: checks prior assistant messages for citations to maintain document search mode across follow-ups

#### Conversation Memory
- **Sliding window**: last MAX_MESSAGES_PER_CONTEXT=12 messages passed to LLM
- **Rolling summarization**: triggered at SUMMARY_TRIGGER_MESSAGES=20; Gemini compresses history into rolling summaries stored in `conversation_summaries`
- `ConversationContextBuilder`: assembles rolling summaries + recent window + current question
- Conversation title auto-generated by `TitleGenerator` on the first assistant response

#### Adaptive RAG Orchestration
- `QueryClassifier`: classifies queries as `direct`, `hyde`, `multi_hop`, or `specialist`
- `SafeHyDEExecutor`: generates hypothetical answer passages via LLM to bridge query-document semantic gaps before dense retrieval
- `QueryDecomposer`: splits compound questions into sequential sub-retrieval queries (MAX_QUERY_SUBTASKS=3)
- `EvidenceSufficiencyEvaluator`: scores retrieved candidate coverage; triggers Replanner if below threshold and budget permits (MAX_AGENT_REPLANS=2)
- `Replanner`: refines query, expands search scope, or escalates strategy

#### Agentic Tool Calling (Single-Agent Loop)
- `AgentExecutor`: LLM function-calling loop, bounded by MAX_TOOL_ITERATIONS=5
- **7 tools in the registry**:
  - `SafeCalculator`: AST-based arithmetic evaluator blocking dangerous operations (import, exec, eval)
  - `WebSearchTool`: multi-provider (SerpAPI -> Firecrawl -> DuckDuckGo auto-selection)
  - `SemanticSearchTool`: full Fusion RAG retrieval callable within the tool loop
  - `ChunkRetrievalTool`: direct chunk lookup by UUID
  - `DocumentRetrievalTool`: document metadata and content retrieval
  - `CitationLookupTool`: resolves inline citation references to source text
  - `DateTimeTool`: returns current UTC timestamp
- Recursion protection, TOOL_EXECUTION_TIMEOUT=30.0s, TOOL_RESULT_SIZE_LIMIT=50000 chars

---

### Phase 3 - Hierarchical Multi-Agent Architecture

#### MasterAgent (Planner)
- Analyzes user intent and produces a JSON ExecutionPlan with tasks: task_id, agent_type, request, dependencies, required_evidence, expected_outputs
- Max 5 tasks per plan; independent tasks have empty dependencies for concurrent execution
- `PlanValidator`: validates JSON schema, checks for cyclic dependencies, enforces allowed agent type policy
- Delegates execution exclusively to `AgentExecutionEngine` -- never executes specialists directly
- Iterative replanning: ResultEvaluator scores task completions against required_evidence; MasterAgent regenerates plan for failed tasks up to MAX_PLAN_ITERATIONS=2

#### AgentExecutionEngine
- Topological sort of task DAG; runs independent tasks concurrently via asyncio.gather
- Per-task timeout: MULTI_AGENT_TASK_TIMEOUT=20.0s
- Preserves results across replan iterations to avoid redundant API calls

#### Four Specialist Agents
- **RESEARCH** (ResearchAgent + ResearchPlanner): LLM-planned sub-queries with cosine deduplication (threshold=0.85), Fusion RAG hybrid retrieval per sub-query, result merging and synthesis
- **DOCUMENT** (DocumentAgent): chunk/document lookup by UUID, scope filtering, metadata inspection, conversation-scoped document listing
- **ANALYSIS** (AnalysisAgent): SafeCalculator for arithmetic, SymPy MathEngine for symbolic math, Python/Pandas script generation for browser-sandboxed dataset analysis
- **WEB_SEARCH** (WebSearchAgent): SerpAPI / Firecrawl / DuckDuckGo, structured result parsing, source URL and snippet extraction

#### TaskRouter & CapabilityRegistry
- Deterministic capability routing: maps AgentType to CapabilityType, validates against CapabilityRegistry
- Budget enforcement: MAX_ESTIMATED_AGENT_COST_UNITS=100, MAX_ESTIMATED_LATENCY_MS=30000
- Optional LLM-advisory routing (ENABLE_LLM_CAPABILITY_ROUTER=False by default; LLM suggestions strictly validated against policy)

#### SynthesisAgent
- Receives all completed AgentResult objects from the execution engine
- Produces a final synthesized, citation-grounded answer via Gemini streaming SSE

#### Agent Observability
- `AgentObservabilityService`: records structured event streams (plan created, task dispatched, task completed, replan triggered)
- Prometheus agent metrics: AGENT_LLM_TOKENS, AGENT_LLM_DURATION, AGENT_REPLANS, AGENT_TASKS_EXECUTED (low-cardinality labels, no user IDs)

---

### Phase 4 - Observability, Evaluation & Production Hardening

#### Production Middleware
- Single `ProductionMiddleware` ASGI middleware handling:
  - Graceful shutdown (503 during drain, active_requests tracking)
  - Request ID correlation (X-Request-ID -- inbound or UUID-generated)
  - JWT resolution and RequestContext population (user_id, role, permissions, client_ip)
  - OTel HTTP server span creation with W3C trace context propagation
  - Prometheus HTTP metrics (requests, duration, in-flight) with low-cardinality parameterized route templates
  - Secure headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP, HSTS in production
  - Structured logging context variables (request_id, method, path, status, duration)

#### OpenTelemetry & Prometheus
- OTel traces exported to Jaeger (:4317 gRPC / :4318 HTTP)
- `TelemetrySanitizer`: strips raw document text, full prompts, API keys from OTel spans
- Prometheus metrics at /api/v1/observability/metrics and /metrics
- Pre-provisioned Grafana dashboards (:3000, admin/admin): Retrieval & Pipeline, LLM & Providers, Queue & Workers, HTTP & API SLO

#### Quality Evaluation Framework
- **Ragas**: Faithfulness, Answer Relevancy, Context Precision, Context Recall
- **DeepEval**: multi-metric LLM-as-judge evaluation
- **Golden datasets**: versioned QA pairs (golden_rag_dataset, golden_multi_agent_v1)
- **10-dimension multi-agent harness**: Planning, DAG Execution, Deterministic Calculation, Refusal Faithfulness, Contradiction Detection, Injection Resistance, Replanning Exhaustion, Web Search Integration, Capability Routing, Result Synthesis
- **Regression governance**: dual-gate (absolute floor AND max degradation from versioned baselines, max_score_drop <= 0.03)
- CI regression runner: backend/scripts/regression.py

#### Production Startup Guards
- `run_startup_validations()`: verifies JWT_SECRET (min 32 chars, no dev placeholders), GEMINI_API_KEY, JINA_API_KEY, ENCRYPTION_MASTER_KEY in production
- Alembic migration version check at startup (fails fast if schema is behind)
- Stale unverified signup cleanup at boot (UNVERIFIED_USER_CLEANUP_DAYS=7)
- `DurableIngestionReaper`: periodic background task recovering stale processing documents
- `DurableCleanupWorker`: processes durable_cleanup_jobs for orphan Qdrant vector and file purging

#### Frontend React SPA
- React 18 + Vite 5 + TypeScript, Vanilla CSS design tokens, dark/light theme toggle
- SSE token streaming with inline citation rendering and citation drawer popups
- Shiki syntax highlighting for code blocks and markdown rendering
- Chat composer with @documents mention support and conversation attachment uploads
- `UploadQueueContext`: manages in-progress conversation attachment uploads
- **Pages**: LandingPage, ChatPage, DocumentsPage, AdminDashboardPage, ProjectsPage, SettingsPage, VerifyEmailPage, OAuthCallbackPage
- **Admin Dashboard** (/admin/dashboard): live KPI tiles, token volume charts, latency distribution, execution trace waterfalls, evaluation report viewer

---

## 5. Out of Scope

- Complex multi-tenant billing, Stripe subscriptions, or SaaS metering
- Visual drag-and-drop workflow graph editors
- Local PyTorch / CUDA model weights (all neural inference is cloud REST API-based)
- Enterprise SAML / Active Directory / LDAP integration

---

## 6. Target Users

1. **Technical Recruiters & Hiring Managers**: Assess depth in RAG architecture, vector databases, agentic AI, distributed systems, and UX engineering
2. **AI Engineers & Developers**: Study, fork, and extend a production-ready Python/React codebase
3. **Local Self-Hosters & Power Users**: Interact privately with personal or team documents (research papers, manuals, financial reports)

---

## 7. Non-Functional Requirements

| Domain | Requirement | Target |
|---|---|---|
| Retrieval Latency | Query rewrite + hybrid search + reranking | < 250 ms (p95, <= 10,000 chunks) |
| Streaming TTFT | Time-to-first-token on SSE streaming | < 600 ms |
| Container Footprint | Zero PyTorch/CUDA weights | Image < 450 MB, cold start < 1 s |
| Groundedness | Absence of hallucinated factual claims | > 90% on golden QA datasets |
| Security | NIST-compliant auth, no hardcoded secrets | Startup fails on invalid production config |
| Concurrency | Non-blocking async, scaled connection pools | 50+ concurrent queries, zero deadlock |
| DB Pool | Tuned to exceed anyio thread pool limits | pool_size=50, max_overflow=50 |
| Cache TTLs | Per-namespace Redis caching | Embedding: 24h; Retrieval: 30m; Rewrite: 2h; LLM: 1h |

---

## 8. Product Principles

1. **Grounded Over Clever**: The assistant prioritizes truthful, citation-backed facts. Refusal is preferred over hallucination.
2. **Total Observability**: The system exposes routing decisions, retrieval scores, replanning events, prompt construction, and token accounting to operators.
3. **Decoupled Architecture**: Ingestion, storage, retrieval, orchestration, and generation are independent components behind well-defined domain interfaces.
4. **Zero-PyTorch Cloud Inference**: Dense vector embeddings, cross-encoder reranking, and LLM generation run exclusively via fast cloud REST APIs. No local GPU required.
5. **Security by Default**: Production mode fails fast if security configuration is absent or uses development placeholders.
6. **Durable by Design**: Background jobs use Redis Streams with consumer groups and ACKs. Document cleanup, stale job recovery, and orphan vector purging all have durable fallback paths.
