# FusionRAG: Production Engineering & Architecture Master Interview

> **Instructions for the Candidate:**
> This interview document contains **37 in-depth technical and situational questions** designed to rigorously test your understanding of the **FusionRAG** production platform. 
> The questions are divided into 7 core engineering domains, ranging from low-level distributed primitives to high-level multi-agent orchestration and incident response.
> 
> Under each question, you will find a designated section:
> ```markdown
> #### Candidate Answer:
> <!-- Write your answer here -->
> ```
> Fill in your technical explanation, architectural rationale, code flow, or incident response strategy directly in that block.

---

## Table of Contents
1. [Domain 1: System Architecture, Mental Model & Design Trade-offs (Q1–Q5)](#domain-1-system-architecture-mental-model--design-trade-offs)
2. [Domain 2: Advanced Hybrid Retrieval, Vector Search & Reranking (Q6–Q11)](#domain-2-advanced-hybrid-retrieval-vector-search--reranking)
3. [Domain 3: Hierarchical Multi-Agent DAG & Orchestration Engine (Q12–Q17)](#domain-3-hierarchical-multi-agent-dag--orchestration-engine)
4. [Domain 4: Security, Isolation, Defense-in-Depth & Prompt Injection (Q18–Q22)](#domain-4-security-isolation-defense-in-depth--prompt-injection)
5. [Domain 5: Distributed Lifecycle, Ingestion & Data Consistency (Q23–Q27)](#domain-5-distributed-lifecycle-ingestion--data-consistency)
6. [Domain 6: Concurrency, Performance Bottlenecks & Scale Engineering (Q28–Q31)](#domain-6-concurrency-performance-bottlenecks--scale-engineering)
7. [Domain 7: Situational Scenarios, Incident Response & Production War Stories (Q32–Q37)](#domain-7-situational-scenarios-incident-response--production-war-stories)
8. [Progress Tracker](#progress-tracker)

---

## Domain 1: System Architecture, Mental Model & Design Trade-offs

### Question 1: Zero-PyTorch Inference Architecture & External REST APIs
**Context & Motivation:**
A conventional RAG stack often loads sentence-transformers and rerankers locally using PyTorch, HuggingFace transformers, and GPU accelerators (CUDA). FusionRAG intentionally eliminates all local PyTorch/CUDA dependencies, routing embedding generation and cross-encoder reranking to external REST APIs (Jina AI) and LLM inference to Google Gemini.
**Key Focus Areas to Address:**
- What are the operational, cold-start, container footprint, and cost advantages of this architecture?
- What are the major trade-offs in terms of network latency, rate limits, external vendor availability, and data sovereignty?
- How does the architecture handle transient network failures or REST API latency spikes during retrieval?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 2: Dual-Layer Orchestration Architecture
**Context & Motivation:**
FusionRAG implements two distinct orchestration layers: a lightweight Adaptive RAG pipeline (`app/rag/orchestration/`) and a full Hierarchical Multi-Agent DAG (`app/chat/services/multi_agent/`).
**Key Focus Areas to Address:**
- Why have two separate orchestration frameworks instead of using the Multi-Agent DAG for everything?
- How does the system classify and route a query between single-turn Adaptive RAG (Direct, HyDE, Multi-hop) and the full Multi-Agent DAG?
- What computational and token overhead does the multi-agent DAG introduce, and when is that overhead justifiable?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 3: PostgreSQL as the Authoritative Transactional Source of Truth
**Context & Motivation:**
In FusionRAG, Qdrant stores dense vectors, Redis holds ephemeral caches and streams, and storage stores binary blobs, but PostgreSQL 16 is strictly designated as the authoritative transactional source of truth.
**Key Focus Areas to Address:**
- Why should Qdrant never be treated as the primary store for document metadata and ownership?
- How does PostgreSQL guarantee relational integrity between users, conversations, documents, chunks, and knowledge graph entities?
- If Qdrant or Redis becomes out of sync or corrupted, how does having PostgreSQL as the source of truth allow full state reconstruction?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 4: Multi-Target Storage Provider Design (Database BLOB vs. Object/File Storage)
**Context & Motivation:**
FusionRAG abstracts file storage behind a unified `StorageProvider` interface, supporting PostgreSQL binary BLOB storage (e.g. for Supabase deployment) and filesystem/object storage.
**Key Focus Areas to Address:**
- What was the architectural rationale behind supporting binary BLOB storage inside PostgreSQL alongside filesystem storage?
- For what scale or deployment environment is PostgreSQL BLOB storage optimal, and at what scale does it become an antipattern?
- How does the storage abstraction prevent leaking physical file paths or storage internals into the domain services?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 5: Multi-Tier Caching (L1/L2/L3) & Active-Version Document Fingerprinting
**Context & Motivation:**
FusionRAG employs a three-tier caching hierarchy: in-memory process cache (L1), distributed Redis (L2), and RAG response cache (L3) with active-version document fingerprinting.
**Key Focus Areas to Address:**
- How is the cache key generated across user ID, thread, parent message, document version signature, and query hash?
- How does "Active-Version Fingerprinting" guarantee zero stale answers when a document is re-indexed or deleted without executing expensive distributed cache purges?
- How does the "Synthetic Paced SSE Stream Replay" preserve frontend typewriter animations and database message persistence on cache hits?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 2: Advanced Hybrid Retrieval, Vector Search & Reranking

### Question 6: Hybrid Retrieval Rationale (Dense vs. Sparse Failure Modes)
**Context & Motivation:**
FusionRAG pairs dense vector similarity search via Qdrant with sparse lexical search via PostgreSQL Full-Text Search (tsvector/GIN) and BM25.
**Key Focus Areas to Address:**
- Why is dense vector search alone inadequate for production document retrieval?
- Give concrete query examples where dense embeddings fail but sparse lexical search succeeds (e.g. part numbers, acronyms, exact identifiers).
- Conversely, give examples where sparse search fails and dense semantic search is required.

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 7: Reciprocal Rank Fusion (RRF) Mechanics & Parameterization
**Context & Motivation:**
Instead of computing a weighted arithmetic sum of cosine similarity and BM25 scores, FusionRAG merges candidate lists using Reciprocal Rank Fusion:
$$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
**Key Focus Areas to Address:**
- Why is direct score normalization (e.g. min-max scaling of cosine similarity vs BM25 raw scores) fragile and prone to calibration drift?
- What role does the smoothing constant $k$ (set to $60$) play in preventing high-ranked outliers from dominating the fused result set?
- What are the computational complexity and memory implications of RRF when merging $M$ candidate lists of size $N$?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 8: Maximal Marginal Relevance (MMR) & Diversity Filtering
**Context & Motivation:**
After candidate fusion, the pipeline applies Maximal Marginal Relevance (MMR) with $\lambda=0.5$ prior to cross-encoder reranking.
**Key Focus Areas to Address:**
- What specific failure mode in chunked document retrieval does MMR address?
- Walk through the mathematical trade-off between relevance to the query $\text{Sim}_1(d_i, q)$ and diversity relative to already selected documents $\max \text{Sim}_2(d_i, d_j)$.
- Why is it critical to run MMR before the Cross-Encoder stage rather than after it?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 9: Cross-Encoder Reranking & Concurrency Bounding
**Context & Motivation:**
FusionRAG utilizes Jina AI's `jina-reranker-v2-base-multilingual` cross-encoder API bounded by an `asyncio.Semaphore(4)`.
**Key Focus Areas to Address:**
- What is the fundamental architectural difference between a bi-encoder (dual-encoder) and a cross-encoder? Why is cross-attention significantly more accurate for passage relevance?
- Why can cross-encoders not be used for initial search across millions of chunks?
- Why did you bound concurrent API reranking calls with an asynchronous semaphore of 4? What happens if this semaphore is omitted during traffic spikes?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 10: Query Preprocessing: HyDE, Query Decomposition & Intent Classification
**Context & Motivation:**
Before querying vector or sparse indexes, queries pass through `QueryClassifier`, `HyDEGenerator`, and `QueryDecomposer`.
**Key Focus Areas to Address:**
- How does Hypothetical Document Embeddings (HyDE) bridge the semantic gap between short questions and long answer passages?
- What is the major risk with HyDE (e.g. hallucinated entities), and how does your pipeline prevent hallucinated text from polluting search vectors?
- How does query decomposition handle complex multi-part questions (e.g. "Compare company X's Q3 revenue with company Y's Q3 revenue")?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 11: Context Budgeting, Token Ceilings & Window Expansion
**Context & Motivation:**
Retrieved chunks cannot simply be dumped into the LLM prompt. FusionRAG uses `ContextSelector` to enforce a strict token ceiling (default 6,000 tokens) alongside parent-child and sentence-window expansion.
**Key Focus Areas to Address:**
- How does the context selector prioritize which chunks to retain when total candidate tokens exceed the budget?
- Explain the difference between indexing small chunks for retrieval accuracy while expanding to parent chunks or sentence windows for LLM synthesis.
- How do you budget prompt tokens across system instructions, conversation history, retrieved context, and expected generation output?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 3: Hierarchical Multi-Agent DAG & Orchestration Engine

### Question 12: Dynamic DAG Construction & Kahn's Algorithm Cycle Prevention
**Context & Motivation:**
`MasterAgent` translates complex user intent into a dependency-aware `ExecutionPlan` where tasks can depend on the outputs of other tasks. `PlanValidator` validates this graph before execution.
**Key Focus Areas to Address:**
- How does the system parse LLM-generated task definitions into a directed acyclic graph (DAG)?
- How does `PlanValidator` use Kahn's algorithm (in-degree counting) to detect cycles and verify topological feasibility?
- What is the fallback mechanism if the LLM generates an invalid graph with circular dependencies or dangling task references?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 13: Topological Wave Execution & Upstream Data Propagation
**Context & Motivation:**
The `AgentExecutionEngine` executes independent tasks concurrently in topological waves ($4.00\times$ measured speedup) rather than executing them sequentially.
**Key Focus Areas to Address:**
- Walk through how tasks are partitioned into Wave 0, Wave 1, etc., based on in-degree and dependencies.
- How are Wave 0 tasks executed concurrently using `asyncio.gather`?
- How does data produced by an upstream specialist (e.g. `TableAgent` extracting tabular numbers) propagate into a downstream specialist (e.g. `AnalysisAgent` computing CAGR)?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 14: AnalysisAgent, SafeCalculator & AST Arithmetic Sandboxing
**Context & Motivation:**
When numerical reasoning is required, FusionRAG forbids the LLM from doing mental math, routing calculations to `AnalysisAgent` backed by `SafeCalculator` and `MathEngine`.
**Key Focus Areas to Address:**
- Why are LLMs notoriously unreliable at mathematical calculations, financial metrics, and CAGR?
- How does `SafeCalculator` use Python's `ast` module to safely parse and evaluate arithmetic expressions?
- What specific attack vectors (e.g. `__import__`, built-in execution, memory exhaustion via exponential power operations like `10**1000000`) does the sandbox block?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 15: Knowledge Graph Representation & Relational Traversal
**Context & Motivation:**
FusionRAG incorporates a Knowledge Graph via `PostgresGraphRetriever` and `GraphTraversalService` querying `graph_entities`, `entity_mentions`, `graph_relationships`, and `relationship_evidence`.
**Key Focus Areas to Address:**
- Why build the knowledge graph inside relational PostgreSQL rather than introducing a separate dedicated graph database like Neo4j?
- How are entities and relationship triples extracted during ingestion, and how are confidence scores recorded?
- How does breadth-first search (BFS) traversal over relationship edges uncover multi-hop connections that dense vector similarity misses?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 16: Adaptive Replanning & Evidence Gate
**Context & Motivation:**
Upon wave completion, `ResultEvaluator` assesses evidence sufficiency before sending context to `SynthesisAgent`. If evidence is contradictory or insufficient, replanning is triggered.
**Key Focus Areas to Address:**
- What specific metrics or heuristics determine that evidence is "inadequate" or "contradictory"?
- How does `MasterAgent` perform targeted replanning without re-executing already successful tasks (preserving success fingerprints)?
- How does the system strictly bound replanning iterations ($\le 2$) to prevent infinite loops and runaway API billing?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 17: Grounded Synthesis, Citation Provenance & Streaming Protocol
**Context & Motivation:**
`SynthesisAgent` produces the final response via Google Gemini using strict XML fencing and citation tags, streamed over Server-Sent Events (SSE).
**Key Focus Areas to Address:**
- How does `SynthesisAgent` link specific claims in the generated response back to `[DocX, ChunkY]` citation provenance?
- How does the prompt instruct the LLM to handle missing evidence (refusal faithfulness) rather than hallucinating?
- Describe the SSE event schema (`metadata`, `thought`, `text`, `citation`, `done`) and how the React frontend renders interactive citations and thought trees.

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 4: Security, Isolation, Defense-in-Depth & Prompt Injection

### Question 18: Dual Document Scope Model (Library vs. Conversation Documents)
**Context & Motivation:**
In FusionRAG, documents are strictly categorized as either `LIBRARY` or `CONVERSATION`.
**Key Focus Areas to Address:**
- What is the invariant regarding `conversation_id` for Library vs. Conversation documents?
- How is this invariant enforced across Pydantic schemas, service validation, and PostgreSQL database `CHECK` constraints?
- What are the security implications if a conversation document is accidentally treated as a library document?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 19: Preventing Model-Supplied Identifier Exploits
**Context & Motivation:**
In an agentic RAG system, an LLM or specialist tool might output a parameter like `document_id="doc_xyz"`.
**Key Focus Areas to Address:**
- Why is it a critical vulnerability to query the database or vector store using an unvalidated model-supplied `document_id`?
- How does `DocumentRetrievalScope` construct an authorized list of document IDs from the authenticated session *before* executing search?
- How does repository-level authorization prevent cross-user and cross-conversation data leakage even if the LLM is jailbroken?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 20: The "Fail-Closed" Principle for Authorization Metadata
**Context & Motivation:**
During early development, a subtle security bug existed: `doc_scope = metadata.get("document_scope") or "LIBRARY"`.
**Key Focus Areas to Address:**
- Why was this fallback dangerous when querying BM25 or Qdrant points with legacy or missing metadata?
- Why must authorization metadata fail closed (i.e. missing metadata $\to$ access denied) rather than falling back to permissive defaults?
- How did the security verification pass detect this, and how was Qdrant migrated to backfill missing scope metadata?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 21: Defense Against Direct & Indirect Prompt Injection
**Context & Motivation:**
RAG systems are uniquely vulnerable to both direct injection (malicious prompt from user) and indirect injection (malicious prompt hidden inside an ingested PDF/webpage).
**Key Focus Areas to Address:**
- What heuristics does `PromptInjectionScanner` employ on `/chat` and `/search` to catch role-play overrides and system prompt extraction?
- How does `PromptBuilder` isolate retrieved document chunks using `<retrieved_context>` XML fencing?
- How do system prompts instruct the LLM that retrieved content is strictly *untrusted data* and never operational instructions?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 22: NIST-Compliant Authentication, JWT Rotation & Replay Attack Defense
**Context & Motivation:**
FusionRAG implements NIST SP 800-63B standards using Argon2id, stateless HS256 JWT access tokens (15m), and single-use HTTP-only refresh cookies (7d).
**Key Focus Areas to Address:**
- Why Argon2id over bcrypt or PBKDF2 for password hashing?
- Explain the single-use rotated refresh token protocol: what happens when a valid refresh token is exchanged?
- How does the system detect a refresh token replay attack, and why does detected reuse immediately trigger revocation of *all* active refresh sessions for that user?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 5: Distributed Lifecycle, Ingestion & Data Consistency

### Question 23: Ingestion Pipeline Sanitization & Antivirus Scanning
**Context & Motivation:**
Uploaded files pass through `MagicByteValidator`, zip-bomb detection, and a streaming ClamAV antivirus scanner before saving.
**Key Focus Areas to Address:**
- Why is checking file extensions or HTTP `Content-Type` headers completely insufficient for secure file uploads?
- How does `MagicByteValidator` verify binary signatures, and how does the zip-bomb defense prevent recursive compression attacks?
- How does the ClamAV daemon socket integration (`clamd` TCP 3310) stream file bytes without writing them to disk first, and why does it fail closed in production?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 24: Asynchronous Processing via Redis Streams vs. Celery
**Context & Motivation:**
Background document enrichment and embedding generation are coordinated using Redis Streams (`RedisStreamTaskQueue`) with consumer groups (`group:document_workers`) rather than Celery or RabbitMQ.
**Key Focus Areas to Address:**
- Why choose Redis Streams over Celery/RabbitMQ for this architecture?
- How do consumer groups, `XREADGROUP`, `XACK`, and visibility timeouts operate in your worker loop?
- How does the retry sorted set (`queue:jobs:retry`) implement exponential backoff and dead-letter queueing for failed ingestion jobs?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 25: The Distributed Deletion Problem & Durable Cleanup Outbox
**Context & Motivation:**
When a user deletes a conversation or document, data must be deleted from PostgreSQL (rows), Qdrant (vectors), Storage (binary files), and Redis (caches).
**Key Focus Areas to Address:**
- If you delete PostgreSQL rows and then call Qdrant API / file deletion, what happens if the server crashes mid-operation?
- Conversely, if you delete external Qdrant vectors first, what happens if the PostgreSQL transaction aborts?
- How does FusionRAG's Durable Cleanup Outbox pattern decouple relational metadata deletion from external resource cleanup to guarantee eventual consistency?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 26: Idempotent External Resource Purging
**Context & Motivation:**
External cleanup workers process deletion jobs asynchronously and may retry multiple times following transient network failures.
**Key Focus Areas to Address:**
- What happens if the worker attempts to delete a Qdrant point or storage file that has already been deleted?
- Why must cleanup operations follow the rule: "Resource already absent = Success"?
- What specific metadata (`storage_key`, `qdrant_point_ids`, `collection_name`) must be stored in the cleanup job record so it can execute without querying deleted database rows?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 27: Self-Healing Ingestion: The Durable Ingestion Reaper
**Context & Motivation:**
If a backend worker pod is killed (OOM, deployment, restart) while processing a 200-page document, the job could remain in limbo forever.
**Key Focus Areas to Address:**
- How does the `DurableIngestionReaper` background task identify stalled or orphaned document processing jobs?
- What lease/heartbeat protocol prevents the reaper from reclaiming a job that is simply taking a long time on a heavy PDF?
- How are recovered jobs safely re-queued without creating duplicate chunks or orphan vectors?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 6: Concurrency, Performance Bottlenecks & Scale Engineering

### Question 28: Resolving the 50-Concurrency Database Connection Pool Deadlock
**Context & Motivation:**
During load testing with 50 concurrent users, FusionRAG experienced a complete server deadlock with 100% request failure rates.
**Key Focus Areas to Address:**
- What was the architectural conflict between FastAPI's asynchronous event loop, `anyio` worker thread pools, and synchronous SQLAlchemy connection pool settings (`pool_size`, `max_overflow`)?
- Why did thread pool starvation lead to a deadlock where all threads were waiting on DB connections while all DB connections were waiting on threads?
- What exact configuration changes (`pool_size=50`, `max_overflow=50`) resolved this issue, taking performance from 0 RPS to 14.58 RPS with 0% errors?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 29: The Decision: Synchronous vs. Async SQLAlchemy
**Context & Motivation:**
In FastAPI, many developers migrate completely to async SQLAlchemy. FusionRAG deliberately maintained a synchronous SQLAlchemy repository layer while optimizing Redis to `redis.asyncio`.
**Key Focus Areas to Address:**
- What was the engineering rationale and risk calculation behind NOT converting the entire SQLAlchemy repository layer to async?
- What would have been the blast radius of such a migration across services, unit-of-work patterns, session lifecycles, and test suites?
- How do you isolate synchronous DB operations from blocking the primary asyncio event loop?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 30: Eliminating the Ingestion N+1 Database Bottleneck
**Context & Motivation:**
Profiling the document ingestion pipeline revealed an N+1 query bottleneck during the embedding generation phase.
**Key Focus Areas to Address:**
- Describe the inefficient N+1 query pattern that was originally querying the database once per chunk for embedding metadata.
- How was this refactored into a single batch query using SQL `.in_()` with an in-memory dictionary lookup?
- What were the measured latency and database CPU reductions resulting from this change?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 31: Bounded LRU Memory Management & BM25 Tokenization Caching
**Context & Motivation:**
In-memory BM25 indexes and query tokenization can rapidly exhaust process memory under multi-tenant load if left unbounded.
**Key Focus Areas to Address:**
- How is the `InMemoryIndexCache` designed with an LRU eviction policy (`INDEX_CACHE_MAX_USERS = 500`) to cap RAM usage?
- Why was repeated tokenization of document chunks during BM25 scoring a CPU bottleneck, and how did class-level pre-tokenization caching resolve it?
- How do you ensure that cached pre-tokenized chunks are invalidated immediately when a user updates or deletes a document?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Domain 7: Situational Scenarios, Incident Response & Production War Stories

### Question 32: Situational Incident — Investigating a Cross-Tenant Data Leak
**Scenario:**
An enterprise customer files an urgent P0 security ticket: an employee querying the bot received retrieved context containing confidential executive salary figures from another department's uploaded spreadsheet.
**Key Focus Areas to Address:**
- Walk through your step-by-step incident response process. How do you triage, contain, and isolate the issue?
- How do you verify whether this was an actual authorization leakage in Qdrant/Postgres, an improper prompt injection bypass, or a pure LLM hallucination?
- What logs (e.g. `DocumentRetrievalScope`, Qdrant payload filters, OpenTelemetry trace spans) would you inspect to prove whether unauthorized chunk IDs were retrieved?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 33: Situational Outage — Upstream Gemini API Quota Exhaustion (HTTP 429)
**Scenario:**
During a live marketing event, query volume quadruples. Google Gemini API begins returning HTTP 429 (Too Many Requests) errors. Multiple concurrent agent DAGs are failing mid-execution.
**Key Focus Areas to Address:**
- How does FusionRAG's multi-key workload isolation (LLM key, Planner key, Fallback key) provide baseline resilience?
- How does the failover proxy and circuit breaker pattern prevent cascading server-side failures?
- How does the agent execution engine degrade gracefully? Can partial evidence gathered by Wave 0 be synthesized, or what user-facing message is streamed over SSE?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 34: Situational Bug — Stale Vector Syndrome after Document Re-upload
**Scenario:**
A user re-uploads an updated version of `company_handbook.pdf` containing new vacation policies. However, when asking questions, the chatbot continues quoting the outdated policies from the old document.
**Key Focus Areas to Address:**
- What components in the pipeline could cause this issue (e.g. SHA-256 deduplication shortcut, cache hit, Qdrant payload versioning, BM25 token cache)?
- How does FusionRAG's active-version document fingerprinting mechanism design prevent this problem?
- If an edge case caused stale vectors to persist, how would you diagnose and purge the stale data?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 35: Situational Attack — Poisoned Document XML Entity / Zip-Bomb Attack
**Scenario:**
An attacker attempts a denial-of-service attack by uploading a seemingly innocuous 1.8 MB `.docx` file crafted with deeply nested XML entities (billion laughs attack) or high-compression zip-bombing designed to expand to 40 GB in memory during parsing.
**Key Focus Areas to Address:**
- At what stage in the ingestion pipeline does FusionRAG inspect and intercept this file?
- What specific checks are performed on file size vs. uncompressed stream expansion ratios ($> 100\times$)?
- How does the application log and drop the connection without crashing the Python process or leaking memory?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 36: Situational Performance Degradation — Diagnosing High P95 Latency
**Scenario:**
Grafana metrics alert that P95 latency on `/chat` has surged from 2.1 seconds to 19.8 seconds over the last hour. CPU utilization on the API server is low (18%), but requests are piling up.
**Key Focus Areas to Address:**
- How do you use OpenTelemetry distributed tracing and Jaeger spans to dissect the request timeline?
- Which potential bottlenecks would you investigate first: Jina cross-encoder semaphore starvation, Qdrant HNSW vector search, PostgreSQL connection pool queueing, or Gemini generation token streaming?
- How would low CPU utilization combined with high latency point to asynchronous semaphore contention or downstream HTTP connection timeouts?

#### Candidate Answer:
<!-- Write your answer here -->

---

### Question 37: Situational Compliance — GDPR Right to be Forgotten & Crypto-Shredding
**Scenario:**
A European user deletes their account and demands immediate verification under GDPR Article 17 ("Right to be Forgotten") that all their proprietary documents and confidential chat histories are permanently irrecoverable, even from Redis persistence dumps and Qdrant disk snapshots.
**Key Focus Areas to Address:**
- How does FusionRAG's envelope encryption architecture (AES-256-GCM with per-user Data Encryption Keys) solve this without re-writing physical database backup files?
- What is "cryptographic shredding," and how does deleting the user's wrapped DEK from `user_encryption_keys` render all historical Redis cache entries and stored vectors permanently unreadable?
- How do you confirm that durable cleanup jobs have purged physical storage objects and relational rows?

#### Candidate Answer:
<!-- Write your answer here -->

---

## Progress Tracker

Use this checklist to track your interview preparation progress:

- [ ] **Domain 1: System Architecture, Mental Model & Design Trade-offs**
  - [ ] Q1: Zero-PyTorch Inference Architecture & External REST APIs
  - [ ] Q2: Dual-Layer Orchestration Architecture
  - [ ] Q3: PostgreSQL as the Authoritative Transactional Source of Truth
  - [ ] Q4: Multi-Target Storage Provider Design
  - [ ] Q5: Multi-Tier Caching (L1/L2/L3) & Active-Version Document Fingerprinting
- [ ] **Domain 2: Advanced Hybrid Retrieval, Vector Search & Reranking**
  - [ ] Q6: Hybrid Retrieval Rationale (Dense vs. Sparse Failure Modes)
  - [ ] Q7: Reciprocal Rank Fusion (RRF) Mechanics & Parameterization
  - [ ] Q8: Maximal Marginal Relevance (MMR) & Diversity Filtering
  - [ ] Q9: Cross-Encoder Reranking & Concurrency Bounding
  - [ ] Q10: Query Preprocessing: HyDE, Decomposition & Intent Classification
  - [ ] Q11: Context Budgeting, Token Ceilings & Window Expansion
- [ ] **Domain 3: Hierarchical Multi-Agent DAG & Orchestration Engine**
  - [ ] Q12: Dynamic DAG Construction & Kahn's Algorithm Cycle Prevention
  - [ ] Q13: Topological Wave Execution & Upstream Data Propagation
  - [ ] Q14: AnalysisAgent, SafeCalculator & AST Arithmetic Sandboxing
  - [ ] Q15: Knowledge Graph Representation & Relational Traversal
  - [ ] Q16: Adaptive Replanning & Evidence Gate
  - [ ] Q17: Grounded Synthesis, Citation Provenance & Streaming Protocol
- [ ] **Domain 4: Security, Isolation, Defense-in-Depth & Prompt Injection**
  - [ ] Q18: Dual Document Scope Model (Library vs. Conversation Documents)
  - [ ] Q19: Preventing Model-Supplied Identifier Exploits
  - [ ] Q20: The "Fail-Closed" Principle for Authorization Metadata
  - [ ] Q21: Defense Against Direct & Indirect Prompt Injection
  - [ ] Q22: NIST-Compliant Authentication, JWT Rotation & Replay Attack Defense
- [ ] **Domain 5: Distributed Lifecycle, Ingestion & Data Consistency**
  - [ ] Q23: Ingestion Pipeline Sanitization & Antivirus Scanning
  - [ ] Q24: Asynchronous Processing via Redis Streams vs. Celery
  - [ ] Q25: The Distributed Deletion Problem & Durable Cleanup Outbox
  - [ ] Q26: Idempotent External Resource Purging
  - [ ] Q27: Self-Healing Ingestion: The Durable Ingestion Reaper
- [ ] **Domain 6: Concurrency, Performance Bottlenecks & Scale Engineering**
  - [ ] Q28: Resolving the 50-Concurrency Database Connection Pool Deadlock
  - [ ] Q29: The Decision: Synchronous vs. Async SQLAlchemy
  - [ ] Q30: Eliminating the Ingestion N+1 Database Bottleneck
  - [ ] Q31: Bounded LRU Memory Management & BM25 Tokenization Caching
- [ ] **Domain 7: Situational Scenarios, Incident Response & Production War Stories**
  - [ ] Q32: Situational Incident — Investigating a Cross-Tenant Data Leak
  - [ ] Q33: Situational Outage — Upstream Gemini API Quota Exhaustion (HTTP 429)
  - [ ] Q34: Situational Bug — Stale Vector Syndrome after Document Re-upload
  - [ ] Q35: Situational Attack — Poisoned Document XML Entity / Zip-Bomb Attack
  - [ ] Q36: Situational Performance Degradation — Diagnosing High P95 Latency
  - [ ] Q37: Situational Compliance — GDPR Right to be Forgotten & Crypto-Shredding
