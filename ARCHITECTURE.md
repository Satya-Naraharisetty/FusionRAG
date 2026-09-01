# System Architecture Manual - Fusion RAG Platform

This document provides an exhaustive architectural specification of the design, pipelines, workflows, and protocols implemented across the **Fusion RAG Platform**.

---

## 1. High-Level System Architecture

The application is structured into decoupled, modular layers: a responsive React SPA frontend (React 18 + Vite 5 + TypeScript + Tailwind CSS v4 + TanStack Query v5), an Nginx reverse proxy gateway, a FastAPI (Python 3.12+) asynchronous application server, authoritative PostgreSQL 16 transactional storage, ephemeral Redis 7 cache and Streams queue, Qdrant vector database, ClamAV antivirus daemon, and upstream REST AI inference providers (Jina AI, Google Gemini, Resend, SerpAPI/Firecrawl).

```mermaid
graph TD
    Browser["React SPA (Client UI: React 18, Vite 5, Tailwind v4, TanStack)"]
    Nginx["Nginx Reverse Proxy (:80 / :443)"]
    FastAPI["FastAPI Web Application (:8000)"]
    Postgres["PostgreSQL Database (Async SQLAlchemy + asyncpg)"]
    Redis["Redis 7 (Cache, Rate Limiter & Streams Task Queue)"]
    Qdrant["Qdrant Vector Database (Cosine ANN, 768-dim)"]
    Jina["Jina AI API (Embeddings & Cross-Encoder Reranker)"]
    Gemini["Google Gemini API (Chat Completion, Vision & Rewrite)"]
    Resend["Resend API (Transactional Email & Magic Links)"]
    ClamAV["ClamAV Daemon (:3310 Antivirus Socket)"]
    WebSearch["Web Search APIs (SerpAPI / Firecrawl / DuckDuckGo)"]
    Storage["Object Storage (S3 / MinIO / Local FS / DB BLOB)"]

    Browser -->|HTTPS / WSS / SSE| Nginx
    Nginx -->|Static UI Assets & PWA| Browser
    Nginx -->|Proxy REST/SSE /api/v1| FastAPI
    FastAPI -->|Credentials, Metadata, FTS, Graph| Postgres
    FastAPI -->|Sliding Rate, Cache, Job Stream| Redis
    FastAPI -->|ANN Dense Vector Search| Qdrant
    FastAPI -->|Dense Vectors & Rerank Scores| Jina
    FastAPI -->|Streaming LLM, Planner, OCR| Gemini
    FastAPI -->|Verification & Magic Link Emails| Resend
    FastAPI -->|Stream Uploaded Bytes| ClamAV
    FastAPI -->|Real-Time Internet Search| WebSearch
    FastAPI -->|Document Binary File I/O| Storage
```

---

## 2. Ingestion & Document Processing Pipeline

The ingestion architecture uses a decoupled two-tier design: fast primary synchronous validation and chunking, followed immediately by asynchronous durable background processing via Redis Streams (`RedisStreamTaskQueue`) for dense embedding generation, multimodal element extraction (tables, figures), and Knowledge Graph construction.

```mermaid
flowchart TD
    Upload["1. POST /api/v1/documents/upload"] --> Magic["2. MagicByteValidator (Signature & Zip-Bomb Check)"]
    Magic --> Malware["3. ClamAVScanner (Fail-Closed Antivirus Scan)"]
    Malware --> Checksum["4. SHA-256 Checksum Deduplication"]
    Checksum --> Storage["5. StorageProvider (Database BLOB, Local FS, or S3)"]
    Storage --> PrimaryProc["6. DocumentProcessingService (Extract & Clean Text)"]
    PrimaryProc --> Chunk["7. ChunkingService (Recursive / Semantic / Parent-Child / Sentence-Window)"]
    Chunk --> SaveDB["8. Batch Insert Chunks into PostgreSQL (document_chunks)"]
    SaveDB --> Complete["9. Commit Primary Transaction & Invalidate Index Cache"]
    
    Complete --> DispatchQueue["10. DurableTaskQueue: Enqueue PROCESS_DOCUMENT / GENERATE_EMBEDDINGS"]
    
    subgraph QueueWorkerArchitecture ["Durable Redis Stream Architecture"]
        DispatchQueue --> Stream["Redis Stream (stream:jobs:document_processing)"]
        Stream --> ConsumerGroup["Consumer Group (group:document_workers)"]
        ConsumerGroup --> Worker["QueueWorker (concurrency=4, visibility_timeout=180s)"]
        Worker -->|Failure & Retry <= 3| RetryQueue["Retry Sorted Set (queue:jobs:retry, backoff=2s..60s)"]
        RetryQueue --> Stream
        Worker -->|Exhausted Retries| DeadLetter["Dead Letter Stream (stream:jobs:dead_letter)"]
        Reaper["DurableIngestionReaper"] -->|Recover Stale Ingestion Jobs| Stream
    end

    Worker --> EmbedJob["11a. Embed Chunks (Jina / Gemini -> Qdrant)"]
    Worker --> EnrichJob["11b. DocumentEnrichmentService (Idempotent Multimodal Extraction)"]
    
    subgraph AsyncEnrichment ["Downstream Enrichment Pipeline"]
        EnrichJob --> ExtractTables["Extract Markdown & CSV Tables -> document_elements (TABLE)"]
        EnrichJob --> ExtractFigures["Extract Images & Diagrams -> document_elements (FIGURE/CHART)"]
        EnrichJob --> ExtractEntities["Extract Named Entities & Mentions -> graph_entities, entity_mentions"]
        ExtractEntities --> ExtractTriples["Construct Relationship Triples -> graph_relationships, relationship_evidence"]
    end
```

---

## 3. Advanced Hybrid Retrieval Pipeline

The retrieval engine coordinates parallel lexical, semantic, tabular, and knowledge graph traversal channels. It supports query preprocessing (HyDE, Query Classification, Expansion, Decomposition), merges candidate sets with Reciprocal Rank Fusion (RRF), filters redundant information using Maximal Marginal Relevance (MMR), applies Cross-Encoder joint cross-attention reranking, and applies hierarchical context expansion (Parent-Child, Sentence-Window).

```mermaid
sequenceDiagram
    autonumber
    participant Client as ChatOrchestrator
    participant Cache as InMemoryIndexCache
    participant QProc as QueryProcessor (Classifier / HyDE / Decomposer)
    participant Retrieval as RetrievalService
    participant FTS as PostgresSparseRetriever / BM25
    participant Qdrant as QdrantDenseRetriever
    participant Graph as PostgresGraphRetriever
    participant Table as DocumentElementRepository
    participant Fusion as ReciprocalRankFusionEngine
    participant MMR as DefaultMMRSelector
    participant Rerank as JinaCrossEncoderReranker (API)
    participant Context as ContextSelector

    Client->>Cache: Check if user has indexed chunks
    Cache-->>Client: Has chunks (proceed) or Empty (skip retrieval)
    Client->>QProc: Process Query (Classify intent: Direct / HyDE / Multi-Hop)
    alt HyDE Enabled & Applicable
        QProc->>QProc: Generate Hypothetical Document Passage
    else Query Decomposition Enabled
        QProc->>QProc: Decompose into Sub-Queries (max 3)
    end
    QProc-->>Retrieval: Prepared Retrieval Query Payload
    Retrieval->>Retrieval: retrieve(query, user_id, scope, conversation_id)
    par Lexical Sparse Search
        Retrieval->>FTS: search(query) via websearch_to_tsquery / BM25
        FTS-->>Retrieval: Top-K Sparse Candidates (lexical scores)
    and Semantic Dense Search
        Retrieval->>Qdrant: search(query_embedding, user_id_filter)
        Qdrant-->>Retrieval: Top-K Dense Candidates (cosine scores)
    and Knowledge Graph Traversal
        Retrieval->>Graph: retrieve_subgraph(query, user_id)
        Graph-->>Retrieval: Entity Relationship Triples & Evidence
    and Structured Tabular Search
        Retrieval->>Table: search_sparse(query, user_id, type=TABLE)
        Table-->>Retrieval: Matching Structured Table Elements
    end
    Retrieval->>Fusion: fuse(dense_results, sparse_results, rrf_k=60)
    Fusion-->>Retrieval: Ranked Candidate List
    Retrieval->>MMR: select(fused, lambda=0.5)
    MMR-->>Retrieval: Diverse Candidate Pool
    Retrieval->>Rerank: rerank(query, candidates) via Jina API (Semaphore=4)
    Rerank-->>Retrieval: Reordered Chunks (rerank relevance scores)
    Retrieval->>Context: apply_token_budget & window_expansion (max_tokens=6000)
    Context-->>Client: Final Bounded SearchResult Payload with Citations
```

---

## 4. Authentication, OAuth & Session Flow

Authentication implements NIST SP 800-63B standards with Argon2id password hashing, stateless JWT HS256 access tokens, single-use rotated HTTP-only refresh cookies, OAuth 2.0 (Google/GitHub), and transactional email verification via Resend.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client Browser
    participant API as FastAPI /api/v1/auth
    participant DB as PostgreSQL (users, refresh_sessions)
    participant Resend as Resend Email Service

    alt Traditional Email/Password Registration
        User->>API: POST /auth/register (Email, Password)
        API->>API: Hash Password (Argon2id)
        API->>DB: Save User (is_active=True, is_verified=False)
        API->>Resend: Dispatch Email Verification Token
        Resend-->>User: Verification Email Link
        User->>API: GET /auth/verify-email?token=...
        API->>DB: Activate User Account (is_verified=True)
    else OAuth 2.0 (Google / GitHub)
        User->>API: GET /auth/oauth/google (or /github)
        API-->>User: Redirect to OAuth Provider
        User->>API: GET /auth/oauth/google/callback (code, state)
        API->>DB: Upsert User by OAuth Subject ID
    end

    User->>API: POST /auth/login (Email, Password)
    API->>API: Rate limit check (5 attempts / 300s window)
    API->>API: Verify Password (Argon2id)
    API->>DB: Create Refresh Session (token_hash, expires_at)
    API-->>User: HTTP-Only Cookie (Refresh Token) + Access Token (JWT, 15m)

    Note over User, API: Standard API requests pass Bearer Access Token in Authorization header

    User->>API: POST /auth/refresh-session (Cookie auto-sent)
    alt Token Valid & Unused
        API->>DB: Rotate Refresh Token (revoke old, issue new)
        API-->>User: New Cookie + Fresh Access Token
    else Token Reused (Replay Attack Detected)
        API->>DB: Revoke ALL User Sessions Immediately
        API-->>User: Clear Cookies & Return 401 Unauthorized
    end
```

---

## 5. History-Aware Retrieval & Conversation Memory

```mermaid
flowchart TD
    Question["Incoming User Question"] --> MentionCheck{"Contains @documents?"}
    MentionCheck -->|Yes| StripMention["Strip @documents, set documents_priority=True"]
    MentionCheck -->|No| StickyCheck{"Prior turn has citations?"}
    StripMention --> StickyCheck
    StickyCheck -->|Yes| SetPriority["Activate documents-priority mode"]
    StickyCheck -->|No| Heuristic
    SetPriority --> Heuristic
    Heuristic["LLMHistoryRewriter: heuristic check (pronouns/follow-ups)"] --> NeedsRewrite{"Needs rewrite?"}
    NeedsRewrite -->|Yes| CacheCheck["Check Redis rewrite cache"]
    CacheCheck -->|Hit| UseCache["Return cached standalone question"]
    CacheCheck -->|Miss| LLMRewrite["Gemini: rewrite using last 6 messages"]
    LLMRewrite --> StoreCache["Store in Redis (TTL 2h)"]
    NeedsRewrite -->|No| UseOriginal["Use original question"]
    UseCache --> Retrieval
    StoreCache --> Retrieval
    UseOriginal --> Retrieval
    Retrieval["Hybrid Retrieval Pipeline"] --> PromptBuild
    PromptBuild["PromptBuilder: system_prompt + XML context + history + question"] --> LLM
    LLM["Gemini SSE Streaming"] --> Persist
    Persist["Persist user & assistant messages with citations"]
    Persist --> SummaryCheck{"Message count > SUMMARY_TRIGGER_MESSAGES?"}
    SummaryCheck -->|Yes| Summarize["Background: Gemini rolling summary -> conversation_summaries"]
    SummaryCheck -->|No| Done
    Summarize --> Done["Done"]
```

---

## 6. Hierarchical Multi-Agent Orchestration Subsystem

The multi-agent execution pipeline orchestrates 7 registered specialist agents via dynamic DAG construction, parallel wave concurrency ($4.00\times$ measured speedup), dependency data propagation, and grounded streaming synthesis.

```mermaid
flowchart TD
    UserQuery["User Query via POST /api/v1/chat"] --> Scan["PromptInjectionScanner (Injection & Role Defense)"]
    Scan --> Master["MasterAgent: LLM Plan Generation (Fallback to Heuristic)"]
    Master --> Validator["PlanValidator (Kahn's Algorithm Cycle & Dependency Check)"]
    Validator -->|Invalid| Regenerate["Regenerate Plan (Bounded Iterations)"]
    Regenerate --> Validator
    Validator -->|Valid| Router["TaskRouter: CapabilityRegistry, Budget & Latency Match"]
    Router --> Engine["AgentExecutionEngine (Topological Wave Execution)"]

    subgraph Wave0 ["Topological Wave 0: Independent Concurrent Tasks (asyncio.gather)"]
        Research["RESEARCH: ResearchAgent (Dense + Sparse + Reranker)"]
        WebS["WEB_SEARCH: WebSearchAgent (Live Web)"]
        DocA["DOCUMENT: DocumentAgent (Chunk/Metadata Inspection)"]
        VisA["VISION: VisionAgent (Diagrams, Figures & OCR)"]
        GraphA["GRAPH: GraphAgent (Knowledge Graph Traversal)"]
    end

    subgraph Wave1 ["Topological Wave 1: Downstream Dependent Tasks"]
        TableA["TABLE: TableAgent (Markdown/CSV Extraction & Aggregation)"]
        Analysis["ANALYSIS: AnalysisAgent (AST SafeCalculator & MathEngine)"]
    end

    Engine --> Wave0
    Wave0 -->|Propagate Upstream Results| Wave1

    Wave0 & Wave1 --> Evaluator["ResultEvaluator (Evidence Sufficiency & Contradiction Check)"]

    Evaluator --> Adequate{Evidence Adequate?}
    Adequate -->|No & Iterations Left| Replan["MasterAgent: Targeted Replanning (Preserves Success Fingerprints)"]
    Replan --> Engine
    Adequate -->|Yes or Max Iterations| Gate["Evidence Relevance Gate (Domain Context Filtering)"]
    Gate --> Synthesis["SynthesisAgent: Grounded Synthesis with XML Context Fencing"]
    Synthesis --> SSE["Server-Sent Events (SSE Stream to Client)"]
```

---

## 7. Security, Isolation & Attack Mitigation Subsystem

Fusion RAG applies defense-in-depth across all system entry points:

1. **Prompt Injection & Jailbreak Defense**:
   - `PromptInjectionScanner`: Pre-flight heuristic detection of role-play instructions, system prompt extraction, delimiter escaping, and override tokens on `/chat` and `/search`.
   - Structured security logging: `PROMPT_INJECTION_BLOCKED` events logged without echoing payload text to stdout.
2. **Context Isolation & Untrusted Framing**:
   - `PromptBuilder` wraps retrieved document chunks strictly inside `<retrieved_context>` XML tags.
   - System prompts instruct the LLM that retrieved text is **strictly untrusted data** and must never be interpreted as instructions.
3. **AST Arithmetic Sandboxing**:
   - `SafeCalculator`: Restricted Abstract Syntax Tree (AST) evaluator for `AnalysisAgent`.
   - Blocks `__import__`, `eval`, `exec`, OS calls, and prevents exponential Denial-of-Service (`base <= 10000`, `exp <= 15`).
4. **Malware Scanning & File Upload Validation**:
   - `MagicByteValidator`: Binary signature checking against MIME types; blocks disguised executables.
   - Zip-bomb defense: Blocks nested archives exceeding 25 MB or an expansion ratio $> 100\times$.
   - `ClamAVScanner`: Streams uploaded bytes to ClamAV daemon (`clamd` TCP 3310), failing closed in production.
5. **Cryptographic Protection & Cursor Signing**:
   - Argon2id password hashing with random per-user salts.
   - Cryptographic envelope encryption: Master Key (`ENCRYPTION_MASTER_KEY`) wraps per-user Data Encryption Keys (`user_encryption_keys`).
   - HMAC SHA-256 keyset cursor signing (`CURSOR_SIGNING_KEY`) prevents pagination tampering.
6. **Multi-Tier Rate Limiting**:
   - Sliding-window Redis rate limiter (`60 req/min`, burst `10`).
   - Strict brute-force guard on `/auth/login`: max 5 attempts per 5-minute window (`300s`).
   - Password-gated account deletion rate limit (`10 req/min`).

---

## 8. Evaluation Framework & Operational Confidence Governance

To prevent regressions, validate complex agentic workflows, and monitor live operations, Fusion RAG enforces a formal multi-tier evaluation system.

### Operational Confidence Categories
1. **Benchmark-Proven**: Offline evaluation over versioned golden datasets (`golden_rag_dataset`, `golden_multi_agent_v1`) measuring quality scores under deterministic execution.
2. **Repository-Proven**: Verified via automated pytest test suites covering retrieval pipelines, agent DAG execution, timeouts, failure cascades, and telemetry sanitization.
3. **Production-Observable**: Fully instrumented with low-cardinality Prometheus metrics (`AGENT_LLM_TOKENS`, `AGENT_LLM_DURATION`, `AGENT_REPLANS`, `AGENT_TASKS_EXECUTED`), OpenTelemetry distributed traces, and sanitized structured JSON logs.

### 10-Dimension Multi-Agent Quality Evaluation
* **Planning & Routing**: Validates correct specialist selection and capability policy enforcement.
* **DAG Execution**: Ensures topological dependency execution and bounded replanning ($\le 2$ iterations).
* **Deterministic Calculation**: Sandboxed arithmetic without LLM numeric hallucinations.
* **Refusal Faithfulness**: Explicit refusal on missing evidence without ungrounded extrapolation.
* **Contradiction Detection**: Identifies conflicting claims across documents, references all sources.
* **Injection Resistance**: Document text treated strictly as untrusted data.
* **Replanning Exhaustion**: Graceful halt at max iterations with diagnostic notices.
* **Web Search Integration**: Accurate real-time information retrieval and result formatting.
* **Capability Routing**: Budget and latency constraint enforcement in `TaskRouter`.
* **Result Synthesis**: Coherent, citation-grounded final answer quality via `SynthesisAgent`.

### Regression Governance (Floor + Maximum Degradation)
* **Dual Gate**: Absolute minimum floor per metric (e.g. faithfulness $\ge 0.90$) AND maximum allowed degradation from versioned baselines (`max_score_drop <= 0.03`).
* **CI Integration**: Automated CLI (`backend/scripts/regression.py`) runs on pull requests to block regressions before merging.

---

## 9. Production Middleware & Request Lifecycle

Every HTTP request passes through a single `ProductionMiddleware` ASGI handler:

```mermaid
flowchart TD
    Req["Incoming HTTP Request"]
    Req --> Drain{"is_draining?"}
    Drain -->|Yes| 503["Return 503 SERVICE_DRAINING"]
    Drain -->|No| ReqID["Extract or Generate X-Request-ID"]
    ReqID --> JWT["Parse JWT -> Populate RequestContext ContextVar"]
    JWT --> OTel["Open OTel Server Span (W3C trace context propagation)"]
    OTel --> Prom["Increment HTTP_SERVER_ACTIVE_REQUESTS"]
    Prom --> Handler["Call Next Handler (route handler)"]
    Handler --> Record["Record Prometheus metrics (requests counter, duration histogram)"]
    Record --> Headers["Inject Secure Headers (CSP, X-Frame-Options, X-Request-ID, HSTS)"]
    Headers --> Cleanup["Decrement active requests, reset ContextVar"]
    Cleanup --> Response["Return Response to Nginx"]
```

---

## 10. Scalability & Resilience

1. **Connection-Pooled Async Redis**: Native `redis.asyncio` connection pooling handles rate limiting, ephemeral caching, and job queuing without blocking the FastAPI event loop.
2. **Thread-Pool Starvation Prevention**: SQLAlchemy database connection pool parameters exceed anyio worker thread limits, eliminating pool starvation deadlocks under heavy concurrency.
3. **Batch DB Ingestion Queries**: Bulk chunk lookups using SQL `.in_()` operations eliminate N+1 database queries during document ingestion.
4. **Shared BM25 Pre-Tokenization Caching**: Class-level tokenization cache reuses CPU-intensive text tokenizations across requests, invalidating selectively on document changes.
5. **Durable Ingestion Reaper**: Non-blocking background asyncio task that periodically recovers stale processing jobs and re-enqueues them.
6. **Durable Cleanup Worker**: Processes `durable_cleanup_jobs` for orphan Qdrant vector and file purging after document deletion.
7. **InMemoryIndexCache**: LRU cache tracking whether a user has any indexed document chunks; prevents unnecessary Qdrant API calls when the knowledge base is empty.
8. **Multi-key Gemini Workload Isolation**: Three separate Gemini API keys (LLM, Planner, Fallback) prevent rate-limit cascades under concurrent agent operations.
9. **Multi-Target Storage Providers**: Supports PostgreSQL binary BLOB, local filesystem, and cloud Object Storage (S3 / MinIO) configured via `STORAGE_PROVIDER`.

---

## 11. API-Driven Retrieval & Zero-PyTorch Architecture

All deep learning inference runs via optimized external REST APIs:

1. **Bi-Encoder Dense Vectors**: Jina AI API (`jina-embeddings-v3`, 768 dimensions) with explicit task flags (`retrieval.passage` for chunks, `retrieval.query` for search queries), or Google Gemini (`text-embedding-004`).
2. **Cross-Encoder Reranking**: Jina AI REST API (`jina-reranker-v2-base-multilingual`) with HTTP connection reuse, bounded concurrency semaphores (`asyncio.Semaphore=4`), and exponential backoff retries.
3. **LLM Generation**: Google Gemini (`gemini-3.5-flash-lite`) for streaming SSE chat completion, Vision OCR, query rewriting, planning, and evaluation.
4. **Runtime Benefits**:
   - Zero PyTorch / CUDA overhead: Backend container image < 450 MB.
   - Instant server startup: sub-second cold start.
   - Zero host GPU dependency: fully operational on standard CPU hardware or free-tier cloud containers (Render, Vercel, Supabase, Upstash).
