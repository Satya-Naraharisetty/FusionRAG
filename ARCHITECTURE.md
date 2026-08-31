# System Architecture Manual - Fusion RAG Chatbot

This document provides a comprehensive architectural specification of the design, pipelines, workflows, and protocols implemented across the **Fusion RAG Chatbot** platform.

---

## 1. High-Level System Architecture

The application is structured into decoupled, modular layers: a responsive React SPA frontend, an Nginx reverse proxy gateway, a FastAPI (Python 3.12+) asynchronous application server, authoritative PostgreSQL transactional storage, ephemeral Redis 7 cache and Streams queue, Qdrant vector database, and upstream REST AI inference providers (Jina AI, Google Gemini, Resend).

```mermaid
graph TD
    Browser["React SPA (Client UI)"]
    Nginx["Nginx Reverse Proxy (:80 / :443)"]
    FastAPI["FastAPI Web Application (:8000)"]
    Postgres["PostgreSQL Database (Async SQLAlchemy)"]
    Redis["Redis 7 (Cache, Rate Limiter & Streams Queue)"]
    Qdrant["Qdrant Vector Database (Cosine ANN)"]
    Jina["Jina AI API (Embeddings & Cross-Encoder Reranker)"]
    Gemini["Google Gemini API (Chat Completion & Vision)"]
    Resend["Resend API (Transactional Email)"]
    ClamAV["ClamAV Daemon (:3310 Antivirus Socket)"]

    Browser -->|HTTPS / WSS / SSE| Nginx
    Nginx -->|Static UI Assets| Browser
    Nginx -->|Proxy REST/SSE /api/v1| FastAPI
    FastAPI -->|Credentials, Metadata, FTS| Postgres
    FastAPI -->|Sliding Rate, Cache, Job Stream| Redis
    FastAPI -->|ANN Dense Vector Search| Qdrant
    FastAPI -->|Dense Vectors & Rerank Scores| Jina
    FastAPI -->|Streaming LLM & OCR Parsing| Gemini
    FastAPI -->|Verification & Magic Link Emails| Resend
    FastAPI -->|Stream Uploaded Bytes| ClamAV
```

---

## 2. Ingestion & Document Processing Pipeline

The ingestion pipeline securely ingests multi-format documents, validates signatures, scans for malware, normalizes text, generates hierarchical chunks, computes dense embeddings, and writes to both SQL and vector stores.

```mermaid
flowchart TD
    Upload["1. POST /api/v1/documents/upload"] --> Magic["2. MagicByteValidator (Signature & Zip-Bomb Check)"]
    Magic --> Malware["3. ClamAVScanner (Fail-Closed Antivirus Scan)"]
    Malware --> Checksum["4. SHA-256 Checksum Deduplication"]
    Checksum --> Storage["5. StorageProvider (PostgreSQL BLOB or Local)"]
    Storage --> Queue["6. Enqueue Job via RedisStreamTaskQueue"]
    Queue --> Worker["7. Background QueueWorker Consumer"]
    Worker --> Extractor["8. ExtractorFactory (PDF, DOCX, TXT, MD, HTML, CSV, Images)"]
    Extractor --> Clean["9. TextCleaner (Whitespace, Boilerplate & Hyphens)"]
    Clean --> Chunk["10. ChunkingService (Recursive / Semantic / Parent-Child / Sentence-Window)"]
    Chunk --> SaveDB["11. Batch Insert Chunks into PostgreSQL (document_chunks)"]
    SaveDB --> BatchEmbed["12. JinaEmbeddingGenerator (jina-embeddings-v3, 768-dim, task=retrieval.passage)"]
    BatchEmbed --> QdrantUpsert["13. Upsert Points into Qdrant (documents collection)"]
    QdrantUpsert --> Complete["14. Update Status COMPLETED & Invalidate InMemoryIndexCache"]
```

---

## 3. Hybrid Retrieval Pipeline

The retrieval engine coordinates parallel lexical and semantic search, combines candidate sets with Reciprocal Rank Fusion (RRF), filters redundant information using MMR, applies Cross-Encoder joint cross-attention reranking, and budgets context to token limits.

```mermaid
sequenceDiagram
    autonumber
    participant Client as ChatOrchestrator
    participant Cache as InMemoryIndexCache
    participant Retrieval as RetrievalService
    participant FTS as PostgresSparseRetriever / BM25
    participant Qdrant as QdrantDenseRetriever
    participant Fusion as ReciprocalRankFusionEngine
    participant MMR as DefaultMMRSelector
    participant Rerank as JinaCrossEncoderReranker (API)
    participant Context as ContextSelector

    Client->>Cache: Check if user has indexed chunks
    Cache-->>Client: Has chunks (proceed) or Empty (skip retrieval)
    Client->>Retrieval: retrieve(query, user_id, scope, conversation_id)
    par Lexical Sparse Search
        Retrieval->>FTS: search(query) via websearch_to_tsquery / BM25
        FTS-->>Retrieval: Top-K Sparse Candidates (lexical scores)
    and Semantic Dense Search
        Retrieval->>Qdrant: search(query_embedding, user_id_filter)
        Qdrant-->>Retrieval: Top-K Dense Candidates (cosine scores)
    end
    Retrieval->>Fusion: fuse(dense_results, sparse_results, rrf_k=60)
    Fusion-->>Retrieval: Ranked Candidate List
    Retrieval->>MMR: select(fused, lambda=0.5)
    MMR-->>Retrieval: Diverse Candidate Pool
    Retrieval->>Rerank: rerank(query, candidates) via Jina API (Semaphore=4)
    Rerank-->>Retrieval: Reordered Chunks (rerank relevance scores)
    Retrieval->>Context: apply_token_budget(chunks, max_tokens=6000)
    Context-->>Client: Final Bounded SearchResult Payload
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
    API->>API: Rate limit check (5/300s window)
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
    Question["Incoming User Question"] --> MentionCheck{"Contains @documents?"\}
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

## 6. Adaptive RAG & Multi-Agent Orchestration

When queries require multi-step reasoning, hypothetical formulation, or external tools, the system executes a dynamic agentic control loop.

```mermaid
flowchart TD
    Query["Standalone User Query"] --> Classify["QueryClassifier (direct / hyde / multi_hop / specialist)"]
    Classify --> Route{Routing Strategy}
    Route -->|direct| DirectRet["Direct Hybrid Retrieval"]
    Route -->|hyde| HyDE["SafeHyDEExecutor (Generate Pseudo-Passage -> Dense Search)"]
    Route -->|multi_hop| Decompose["QueryDecomposer (Split Subtasks -> Sequential Retrieval)"]
    Route -->|specialist| MultiAgent["MasterAgent (DAG Planning -> AgentExecutionEngine)"]

    DirectRet --> Evidence
    HyDE --> Evidence
    Decompose --> Evidence
    MultiAgent --> Evidence["EvidenceSufficiencyEvaluator"]

    Evidence --> Sufficient{Evidence Adequate?}
    Sufficient -->|No & Replans Remaining| Replan["Replanner (Refine / Expand / Escalate)"]
    Replan --> Route
    Sufficient -->|Yes or Timeout| ToolCheck{Tool Calls Required?}

    ToolCheck -->|Math| SafeCalc["SafeCalculator (AST-Sandboxed)"]
    ToolCheck -->|Web| WebSearch["WebSearchTool (SerpAPI / Firecrawl / DuckDuckGo)"]
    ToolCheck -->|RAG| SemanticSearch["SemanticSearchTool"]
    SafeCalc --> Synthesis
    WebSearch --> Synthesis
    SemanticSearch --> Synthesis
    ToolCheck -->|Direct| Synthesis["PromptBuilder (retrieved_context XML Fencing)"]

    Synthesis --> Gemini["Google Gemini (gemini-3.5-flash-lite)"]
    Gemini --> SSE["Server-Sent Events (SSE Stream to Client)"]
```

---

## 7. Hierarchical Multi-Agent Execution

The MasterAgent decomposes complex user requests into a typed DAG of specialist tasks executed concurrently by the AgentExecutionEngine.

```mermaid
flowchart TD
    UserQuery["Complex User Query"] --> Master["MasterAgent: LLM Plan Generation"]
    Master --> Validator["PlanValidator (schema + cycle check + policy)"]
    Validator -->|Invalid| Regenerate["Regenerate Plan"]
    Regenerate --> Validator
    Validator -->|Valid| Engine["AgentExecutionEngine (Topological Sort)"]

    Engine --> Wave0["Wave 0: Independent Tasks (asyncio.gather)"]
    Wave0 --> Research["RESEARCH: ResearchAgent + ResearchPlanner"]
    Wave0 --> WebS["WEB_SEARCH: WebSearchAgent"]
    Wave0 --> DocA["DOCUMENT: DocumentAgent"]

    Wave0 --> Wave1["Wave 1: Dependent Tasks"]
    Wave1 --> Analysis["ANALYSIS: AnalysisAgent"]

    Research --> Evaluator
    WebS --> Evaluator
    DocA --> Evaluator
    Analysis --> Evaluator["ResultEvaluator (score vs required_evidence)"]

    Evaluator --> Adequate{All Tasks Passed?}
    Adequate -->|No & Iterations Left| Replan["MasterAgent: Regenerate Plan for Failed Tasks"]
    Replan --> Engine
    Adequate -->|Yes or Max Iterations| Synthesis["SynthesisAgent: Final Citation-Grounded Answer"]
    Synthesis --> SSE["SSE Stream to Client"]
```

---

## 8. Evaluation Framework & Operational Confidence Governance

To prevent regressions, validate complex agentic workflows, and monitor live operations, Fusion RAG enforces a formal multi-tier evaluation system.

### Operational Confidence Categories
1. **Benchmark-Proven**: Offline evaluation over versioned golden datasets measuring quality scores under deterministic execution
2. **Repository-Proven**: Verified via automated pytest test suites (66+ test files) covering retrieval pipelines, agent DAG execution, timeouts, failure cascades, and telemetry sanitization
3. **Production-Observable**: Fully instrumented with low-cardinality Prometheus metrics (AGENT_LLM_TOKENS, AGENT_LLM_DURATION, AGENT_REPLANS, AGENT_TASKS_EXECUTED), OpenTelemetry distributed traces, and sanitized structured JSON logs

### 10-Dimension Multi-Agent Quality Evaluation
* **Planning & Routing**: Validates correct specialist selection and capability policy enforcement
* **DAG Execution**: Ensures topological dependency execution and bounded replanning (<= 2 iterations)
* **Deterministic Calculation**: Sandboxed arithmetic without LLM numeric hallucinations
* **Refusal Faithfulness**: Explicit refusal on missing evidence without ungrounded extrapolation
* **Contradiction Detection**: Identifies conflicting claims across documents, references all sources
* **Injection Resistance**: Document text treated strictly as untrusted data
* **Replanning Exhaustion**: Graceful halt at max iterations with diagnostic notices
* **Web Search Integration**: Accurate real-time information retrieval and result formatting
* **Capability Routing**: Budget and latency constraint enforcement in TaskRouter
* **Result Synthesis**: Coherent, citation-grounded final answer quality via SynthesisAgent

### Regression Governance (Floor + Maximum Degradation)
* **Dual Gate**: Absolute minimum floor per metric (e.g. faithfulness >= 0.90) AND maximum allowed degradation from versioned baselines (max_score_drop <= 0.03)
* **CI Integration**: Automated CLI (backend/scripts/regression.py) runs on pull requests to block regressions before merging

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

1. **Connection-Pooled Async Redis**: Native `redis.asyncio` connection pooling handles rate limiting, ephemeral caching, and job queuing without blocking the FastAPI event loop
2. **Thread-Pool Starvation Prevention**: SQLAlchemy database connection pool parameters (`pool_size=50`, `max_overflow=50`) exceed anyio worker thread limits, eliminating pool starvation deadlocks under heavy concurrency
3. **Batch DB Ingestion Queries**: Bulk chunk lookups using SQL `.in_()` operations eliminate N+1 database queries during document ingestion
4. **Shared BM25 Pre-Tokenization Caching**: Class-level tokenization cache reuses CPU-intensive text tokenizations across requests, invalidating selectively on document changes
5. **Durable Ingestion Reaper**: Non-blocking background asyncio task that periodically recovers stale processing jobs and re-enqueues them
6. **Durable Cleanup Worker**: Processes `durable_cleanup_jobs` for orphan Qdrant vector and file purging after document deletion
7. **InMemoryIndexCache**: LRU cache tracking whether a user has any indexed document chunks; prevents unnecessary Qdrant API calls when the knowledge base is empty
8. **Multi-key Gemini Workload Isolation**: Three separate Gemini API keys (LLM, Planner, Fallback) prevent rate-limit cascades under concurrent agent operations

---

## 11. API-Driven Retrieval & Zero-PyTorch Architecture

All deep learning inference runs via optimized external REST APIs:

1. **Bi-Encoder Dense Vectors**: Jina AI API (`jina-embeddings-v3`, 768 dimensions) with explicit task flags (`retrieval.passage` for chunks, `retrieval.query` for search queries), or Google Gemini (`text-embedding-004`)
2. **Cross-Encoder Reranking**: Jina AI REST API (`jina-reranker-v2-base-multilingual`) with HTTP connection reuse, bounded concurrency semaphores (asyncio.Semaphore=4), and exponential backoff retries
3. **LLM Generation**: Google Gemini (`gemini-3.5-flash-lite`) for streaming SSE chat completion, Vision OCR, query rewriting, planning, and evaluation
4. **Runtime Benefits**:
   - Zero PyTorch / CUDA overhead: Backend container image < 450 MB
   - Instant server startup: sub-second cold start
   - Zero host GPU dependency: fully operational on standard CPU hardware or free-tier cloud containers (Render, Vercel, Supabase)
