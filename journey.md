
# Hybrid RAG Chatbot — Engineering Journey & Interview Journal

## Project Retrospective

**Project:** Production-Grade Hybrid RAG Chatbot
**Status:** Completed and deployed
**Primary objective:** Build, harden, verify, optimize, and deploy a production-oriented Hybrid Retrieval-Augmented Generation system.

---

# 1. Why I Built This Project

The original objective was not simply to build a chatbot that could answer questions from documents.

The goal was to build a **production-grade Hybrid RAG system** that could demonstrate the engineering problems surrounding a real AI application:

* Authentication and authorization
* Document ingestion
* Document processing
* Chunking
* Embedding generation
* Vector search
* Sparse/BM25 search
* Hybrid retrieval
* Reranking/retrieval optimization
* Conversational context
* Agent/tool-based retrieval
* Document-level security
* Persistent storage
* Background processing
* Cleanup and resource lifecycle management
* Caching
* Rate limiting
* Observability
* Scalability
* Testing
* Deployment

The project therefore evolved from being primarily a **RAG implementation** into a broader exercise in **production AI system engineering**.

---

# 2. The Initial Mental Model

At the beginning, the system could be thought of relatively simply:

```text
User
  ↓
Chat API
  ↓
Retrieve relevant documents
  ↓
Hybrid Search
  ├── Dense Search → Qdrant
  └── Sparse Search → BM25
  ↓
Combine / Rank Results
  ↓
LLM
  ↓
Answer
```

The initial focus was therefore retrieval quality.

Very quickly, however, it became clear that retrieval quality alone was not enough.

A production system has to answer questions such as:

> Who is allowed to retrieve this document?

> What happens when a conversation is deleted?

> What happens to its vectors?

> What happens if the storage deletion fails?

> Can a model-generated document ID bypass authorization?

> What happens when 50 users query the system simultaneously?

> Can an old vector without the new security metadata accidentally become visible?

These questions eventually drove some of the most important architectural changes.

---

# 3. Initial Development Roadmap

The original development approach followed a staged engineering workflow:

```text
Requirements
    ↓
Architecture
    ↓
Design
    ↓
Implementation
    ↓
Verification
    ↓
Refactoring
    ↓
Performance
    ↓
Deployment
```

The initial roadmap covered:

1. Foundation
2. Authentication
3. Document management
4. Document processing
5. Embeddings
6. Sparse retrieval / BM25
7. Dense retrieval / Qdrant
8. Hybrid retrieval / RRF
9. Retrieval optimization
10. LLM/chat
11. Evaluation
12. Observability
13. Security
14. Performance
15. Production release

One important lesson from this stage was:

> **Do not optimize or expand the system before establishing the correct architectural boundaries.**

That principle became particularly important later.

---

# 4. The Core Architecture

The resulting system became a multi-layer architecture rather than a single RAG pipeline.

At a high level:

```text
                         ┌───────────────┐
                         │    Frontend   │
                         └───────┬───────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │    FastAPI    │
                         │      API      │
                         └───────┬───────┘
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                  ▼                             ▼
          ┌───────────────┐             ┌───────────────┐
          │ Chat/Agent    │             │ Document API  │
          │ Orchestrator  │             │               │
          └───────┬───────┘             └───────┬───────┘
                  │                             │
                  ▼                             ▼
          ┌────────────────────────────────────────────┐
          │             Domain / Services              │
          └─────────────────────┬──────────────────────┘
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
        PostgreSQL           Qdrant             BM25
        Source of Truth      Dense              Sparse
                             Retrieval          Retrieval
             │
             ▼
       Storage / Files

       Redis
       ├── Cache
       ├── Rate limiting
       ├── Locks
       └── Event/stream infrastructure
```

The important architectural principle was that PostgreSQL remained the **source of truth for authorization and document metadata**.

External systems such as Qdrant and file storage were treated as derived/external resources.

---

# 5. First Major Challenge — Hybrid Retrieval

The first major technical challenge was implementing retrieval using both sparse and dense approaches.

Dense retrieval provides semantic similarity.

Sparse retrieval provides lexical matching.

Neither approach is universally sufficient.

The system therefore evolved toward:

```text
User Query
    │
    ├───────────────┐
    ▼               ▼
Dense Search     BM25 Search
(Qdrant)         (Sparse)
    │               │
    └───────┬───────┘
            ▼
      Hybrid Ranking
            │
            ▼
        Retrieved
        Context
            │
            ▼
           LLM
```

This introduced additional complexity:

* Two retrieval engines
* Different filtering mechanisms
* Different representations
* Consistency requirements
* Duplicate results
* Ranking differences
* Cache considerations

The eventual lesson was:

> **Hybrid retrieval is not merely "run two searches." Both retrieval paths must enforce exactly the same authorization and scope semantics.**

That became extremely important during the security work.

---

# 6. The Dual Document Scope Problem

One of the biggest architectural discoveries was that the system actually had **two fundamentally different types of documents**.

### Library documents

Persistent documents belonging to the user.

```text
User
 └── Library Documents
```

### Conversation documents

Documents attached specifically to one conversation.

```text
User
 └── Conversation
       └── Conversation Documents
```

These cannot safely be treated as the same logical scope.

This led to the explicit domain model:

```python
class DocumentScope(str, Enum):
    LIBRARY = "LIBRARY"
    CONVERSATION = "CONVERSATION"
```

With the invariant:

```text
LIBRARY
    → conversation_id MUST be NULL

CONVERSATION
    → conversation_id MUST NOT be NULL
```

This invariant was enforced at multiple layers:

```text
Pydantic/domain validation
        ↓
Service validation
        ↓
Database CHECK constraint
        ↓
Retrieval authorization
        ↓
Vector filtering
        ↓
Sparse filtering
        ↓
Agent tools
```

This was one of the most important architectural decisions in the project.

---

# 7. The @documents Retrieval Intent

A second problem emerged:

### What should normal chat search?

The desired behavior became:

```text
Normal chat
    → conversation documents only
```

Whereas:

```text
@documents query
    → conversation documents
      +
      user's library documents
```

This resulted in an explicit intent parser.

The parser detects:

```text
@documents
```

at valid token boundaries, removes it from the query, and produces an explicit intent.

Conceptually:

```text
User Query
     ↓
DocumentScopeIntentParser
     ↓
┌───────────────────────────────┐
│ cleaned_query                 │
│ include_library_documents     │
└───────────────────────────────┘
```

This was preferable to scattering string checks throughout the application.

The important lesson:

> **User intent should be represented as a domain concept rather than inferred repeatedly by individual components.**

---

# 8. Retrieval Security Became a Major Challenge

One of the hardest parts of the project was realizing that authorization could not stop at the API layer.

Suppose a malicious or incorrectly behaving LLM produces:

```text
document_id = somebody_else's_document
```

Simply trusting the model-provided ID would be a serious security vulnerability.

Therefore the retrieval architecture became:

```text
User Query
    ↓
RetrievalScope
    ↓
Allowed Document IDs
    ↓
Repository Authorization
    ↓
Dense / Sparse Retrieval
```

The system explicitly constructed:

```python
DocumentRetrievalScope(
    user_id=...,
    conversation_id=...,
    include_conversation_documents=...,
    include_library_documents=...,
    document_ids=...,
)
```

The repository then independently determined which documents were actually allowed.

This gave us an important security property:

> **Model-supplied identifiers are never treated as authorization.**

---

# 9. Agent Tool Security

The agent/tool layer created another security boundary.

Tools included functionality such as:

* Semantic search
* Document retrieval
* Chunk retrieval
* Citation lookup

Initially, it was tempting to let the tool receive a list of allowed document IDs.

That approach was eventually replaced with explicit scope semantics.

The `ToolContext` became:

```python
include_library_documents: bool = False
include_conversation_documents: bool = True
```

This replaced the fragile:

```text
None = library allowed
[]   = library denied
```

implicit convention.

The new architecture became:

```text
ChatOrchestrator
       ↓
ToolContext
       ↓
Agent Tool
       ↓
Repository / RetrievalService
       ↓
Independent authorization
```

A model could therefore obtain a chunk ID from one conversation and attempt to retrieve it from another conversation.

The tool would still reject the request because:

```text
user ownership
        +
conversation scope
```

were independently verified.

---

# 10. The Most Important Security Principle

The final security model became:

```text
Authentication
      ↓
Ownership
      ↓
Document Scope
      ↓
Conversation Scope
      ↓
Retrieval Permission
      ↓
Actual Retrieval
```

Not:

```text
Frontend filter
      ↓
Trust the request
```

And not:

```text
LLM says document X
      ↓
Retrieve document X
```

The system instead follows a defense-in-depth model.

---

# 11. Conversation Deletion — The Hardest Lifecycle Problem

One of the most difficult parts of the project was conversation deletion.

A conversation document does not exist in only one place.

A single uploaded document may produce:

```text
PostgreSQL
 ├── Document metadata
 ├── Chunks
 └── Embedding metadata

Qdrant
 └── Vector points

Storage
 └── Physical document

Caches
 └── Derived index/cache entries
```

Deleting only the PostgreSQL row would therefore create orphaned external resources.

Deleting external resources first would create another problem:

```text
Delete Qdrant
   ↓
Crash
   ↓
Postgres transaction never completes
```

The system could become inconsistent.

---

# 12. Durable Cleanup Outbox

The solution was a durable cleanup job.

The architecture became:

```text
Conversation Delete
        ↓
PostgreSQL Transaction
        │
        ├── Find conversation documents
        ├── Capture external resource IDs
        ├── Create cleanup job
        ├── Delete DB metadata
        └── Delete/soft-delete conversation
        ↓
      COMMIT
        ↓
Async Cleanup Worker
        ├── Qdrant deletion
        ├── Storage deletion
        ├── Cache invalidation
        └── Retry on failure
```

The cleanup job stores enough information to perform external deletion **without depending on database rows that have already been deleted**.

For example:

```text
document_id
user_id
conversation_id
storage_key
qdrant_collection_name
qdrant_point_ids
resource_type
```

This was a crucial durability decision.

---

# 13. Why the Cleanup Job Was Necessary

Consider this failure:

```text
Postgres transaction
       ↓
cleanup job created
       ↓
DB records deleted
       ↓
application crashes
```

Without a durable job:

```text
External resources remain forever
```

With a durable job:

```text
Server restarts
       ↓
PENDING job discovered
       ↓
Cleanup resumes
```

This transforms cleanup from a best-effort operation into a **durable workflow**.

---

# 14. Idempotence

Another challenge was ensuring cleanup could safely run multiple times.

For example:

```text
Qdrant point already deleted
Storage object already deleted
```

These should not be treated as catastrophic failures.

The worker therefore follows the principle:

```text
Already absent
      ↓
Treat as success
```

This enables:

```text
retry
restart
duplicate execution
manual recovery
```

without corrupting state.

---

# 15. Qdrant Migration Challenge

Once document scope became part of authorization, existing Qdrant points became a problem.

Old vectors did not necessarily contain:

```text
document_scope
conversation_id
user_id
document_id
```

The dangerous solution would have been:

```python
scope = payload.get("document_scope") or "LIBRARY"
```

That was explicitly rejected.

Why?

Because:

```text
missing metadata
      ≠
library document
```

Instead:

```text
missing document_scope
      ↓
REJECT
```

This became an important security lesson:

> **Never convert missing authorization metadata into a permissive default.**

---

# 16. Qdrant Migration and Verification

A migration utility was introduced with three modes:

```text
--dry-run
--apply
--verify
```

The migration process became:

```text
SQL Truth
   ↓
Compare with Qdrant
   ↓
Backfill payload
   ↓
Verify
```

The live migration produced:

```text
3 points required document_scope backfill
19 orphan points discovered

3 points updated
19 orphan points skipped

Verification:
exit 0
```

The orphan vectors were legacy resources whose PostgreSQL records had already been deleted before the durable cleanup mechanism existed.

They were therefore treated as data-hygiene warnings rather than scope-integrity failures.

---

# 17. Sparse Retrieval Security Issue

Another subtle issue appeared in BM25.

The code originally had behavior equivalent to:

```python
doc_scope = metadata.get("document_scope") or "LIBRARY"
```

This looked harmless.

It was not.

An old or malformed chunk without scope metadata would silently become a library document.

The fix was:

```text
document_scope missing
        ↓
exclude chunk
```

This is an example of a bug that may pass ordinary functional testing but fail security review.

---

# 18. Verification Pass

After the main implementation, a dedicated security verification pass was performed.

Six issues were discovered and fixed:

1. Implicit `None` vs list authorization signal
2. Missing Qdrant filterable fields
3. Sparse retrieval library fallback
4. Search API backward-compatible retrieval fallback
5. DB query occurring before empty-scope fast path
6. Migration script database-session import issue

This was an important milestone.

The project demonstrated that:

> **Passing functional tests does not necessarily mean the architecture is secure.**

A separate verification pass was required.

---

# 19. Security Test Suite

Twelve additional security tests were introduced.

They covered:

* Default ToolContext security
* `@documents` library access
* Removal of the old implicit authorization field
* Empty retrieval scope
* Per-user library scope
* No unnecessary DB query
* Tool propagation of library intent
* Model-injected foreign document IDs
* Library chunk denial without explicit intent
* Cross-conversation chunk denial
* Missing sparse scope rejection
* Cross-user retrieval denial

The broader suite reached:

```text
168 tests
168 passed
```

Later scalability work increased the complete suite to:

```text
195 tests
195 passed
```

---

# 20. Scalability Problems Appeared

Once correctness and security were established, another class of problems appeared:

> The system worked, but how would it behave under concurrency?

The investigation identified several potential bottlenecks:

* Synchronous Redis operations on async paths
* Ingestion N+1 queries
* Unbounded in-memory indexing
* Repeated BM25 tokenization
* Cleanup recovery concerns
* Database connection-pool pressure

The original idea of wrapping synchronous SQLAlchemy repository operations in `asyncio.to_thread()` was deliberately reconsidered.

---

# 21. Why We Did NOT Convert SQLAlchemy to Async

A full async SQLAlchemy migration would have affected:

* repositories
* unit-of-work logic
* services
* routes
* tests
* session lifecycle
* dependency injection

That would have significantly increased risk.

The final decision was:

> **Keep the synchronous SQLAlchemy repository architecture internally consistent.**

This was a deliberate engineering trade-off.

Instead of rewriting the database architecture, optimization focused on areas where asynchronous improvements were safer.

---

# 22. Async Redis Optimization

Redis interactions were moved to `redis.asyncio`.

The lifecycle became:

```text
Application Startup
      ↓
Create Redis connection pool
      ↓
Create Redis async client
      ↓
app.state.redis
      ↓
Application Runtime
      ↓
Reuse shared client
      ↓
Application Shutdown
      ↓
Close client
      ↓
Disconnect pool
```

Components updated included:

* Rate limiter
* Redis cache
* Redis event bus
* Distributed lock

This removed synchronous Redis operations from async execution paths.

---

# 23. Ingestion N+1 Problem

Another significant performance issue was discovered in embedding generation.

The inefficient pattern was conceptually:

```text
for chunk in chunks:
    query database for embedding
```

For N chunks:

```text
N database queries
```

The optimized approach became:

```text
chunk IDs
    ↓
one batch query
    ↓
embedding records
    ↓
dictionary indexed by chunk_id
    ↓
in-memory lookups
```

Conceptually:

```python
embeddings = repository.get_by_chunk_ids(chunk_ids)

embedding_map = {
    embedding.chunk_id: embedding
    for embedding in embeddings
}
```

This transformed the database interaction from an N+1 pattern to a batch operation.

---

# 24. Memory Growth in the In-Memory Index

The in-memory BM25/index cache presented another production concern.

Without a capacity limit:

```text
Users
  ↓
Indexes
  ↓
Memory continuously grows
```

The solution was an LRU cache.

```text
Most recently used
        ↓
        A
        B
        C
        D
        ↓
Least recently used
```

When capacity is exceeded:

```text
remove oldest
```

The maximum number of cached users became configurable:

```text
INDEX_CACHE_MAX_USERS = 500
```

Thread synchronization was also added around cache operations.

---

# 25. BM25 Pre-Tokenization Optimization

BM25 retrieval was also optimized.

Previously, chunks could be repeatedly tokenized during retrieval/index operations.

The optimized model became:

```text
Raw Chunk
    ↓
Tokenize once
    ↓
Cached token representation
    ↓
BM25
```

The cache was also designed with cleanup/pruning behavior so that optimization did not simply create another memory leak.

An important constraint remained:

```text
Do not sacrifice document-scope isolation for performance.
```

---

# 26. Database Connection Pool Bottleneck

During high-concurrency testing, a more serious operational issue appeared.

At around 50 concurrent users, the server could become effectively starved.

The investigation showed database connection-pool pressure.

The connection pool was increased to:

```text
pool_size = 50
max_overflow = 50
```

This eliminated the observed high-concurrency deadlock in the tested environment.

This was a good example of why:

> **Load testing can reveal problems that unit tests cannot.**

---

# 27. The Load Testing Milestone

A repeatable concurrent load-test script was created using asynchronous HTTP clients.

The benchmark measured:

* Requests per second
* p50 latency
* p95 latency
* Error rate

Concurrency levels included:

```text
10
25
50
```

---

# 28. Before vs After

### Baseline

```text
Concurrency 10
10.51 RPS
p50: 678.5 ms
p95: 1509.7 ms
Errors: 0%

Concurrency 25
10.55 RPS
p50: 2230.8 ms
p95: 2423.3 ms
Errors: 0%

Concurrency 50
12.86 RPS
p50: 0 ms
p95: 0 ms
Errors: 100%
Deadlock
```

### Optimized

```text
Concurrency 10
11.61 RPS
p50: 627.5 ms
p95: 1377.3 ms
Errors: 0%

Concurrency 25
12.22 RPS
p50: 1957.7 ms
p95: 2155.8 ms
Errors: 0%

Concurrency 50
14.58 RPS
p50: 2580.7 ms
p95: 4144.1 ms
Errors: 0%
```

The most important result was not simply the increase in RPS.

It was:

```text
50 concurrent requests
        ↓
Previously: 100% failure
        ↓
After:
14.58 RPS
0% error
```

The high-concurrency deadlock was resolved in the tested environment.

---

# 29. Durable Cleanup Recovery

The cleanup lifecycle was then tested end-to-end against the real services.

The flow was:

```text
Upload conversation document
        ↓
Postgres document
        ↓
Chunks
        ↓
Embeddings
        ↓
Qdrant vectors
        ↓
Physical storage
```

Then:

```text
Delete conversation
        ↓
Postgres transaction
        ↓
Create durable cleanup job
        ↓
Delete relational records
        ↓
Commit
        ↓
Cleanup worker
        ├── Qdrant
        ├── Storage
        └── Cache
```

The system was also tested under simulated external failures.

Failed jobs remained durable and could later be retried successfully.

---

# 30. Final Verification Milestone

The final verification established:

```text
195 / 195 tests passing
```

The important categories included:

```text
Security
Chat
Agent tools
Retrieval
Embeddings
Cleanup
Caching
Scoping
Integration
```

The live cleanup lifecycle was also verified.

The final Qdrant migration verification completed successfully.

The high-concurrency deadlock was resolved.

---

# 31. Deployment

After the implementation and verification phases, the project was deployed.

The deployment architecture followed the production-oriented separation of responsibilities:

```text
Frontend
    ↓
Backend API
    ↓
PostgreSQL
    ↓
Redis
    ↓
Qdrant
    ↓
Object/File Storage
```

The important lesson from deployment was that deployment is not the final substitute for engineering verification.

The system first had to satisfy:

```text
Correctness
+
Security
+
Durability
+
Performance
+
Operational recovery
```

and only then move toward deployment.

---

# 32. Project Milestones

## Milestone 1 — Foundation

Established the application architecture, backend, database, authentication, document handling, and core services.

---

## Milestone 2 — Hybrid RAG

Implemented:

```text
Dense Retrieval
+
Sparse Retrieval
+
Hybrid Ranking
+
LLM Generation
```

---

## Milestone 3 — Production Document Lifecycle

Introduced:

```text
Library documents
Conversation documents
```

with explicit ownership and lifecycle rules.

---

## Milestone 4 — Retrieval Security

Introduced:

```text
DocumentRetrievalScope
```

and enforced it across:

* PostgreSQL
* Qdrant
* BM25
* Retrieval service
* Agent tools
* Chat orchestration
* Search API

---

## Milestone 5 — Durable Cleanup

Implemented:

```text
Durable cleanup jobs
+
External resource deletion
+
Retries
+
Idempotence
+
Startup recovery
```

---

## Milestone 6 — Security Verification

Found and fixed six subtle issues.

Added twelve dedicated security tests.

Reached:

```text
168/168 tests passing
```

---

## Milestone 7 — Scalability

Optimized:

* Redis
* Embedding ingestion
* Index cache
* BM25
* Database connection pooling

---

## Milestone 8 — Load Testing

Discovered and eliminated the 50-concurrency deadlock.

Final benchmark:

```text
50 concurrency
14.58 RPS
0% errors
```

---

## Milestone 9 — Final Validation

Final suite:

```text
195/195 tests passing
```

Live Qdrant migration verified.

Cleanup lifecycle verified against live infrastructure.

---

## Milestone 10 — Deployment

Production deployment completed.

---

# 33. The Most Challenging Part of the Project

If asked in an interview:

> **"What was the hardest part of the project?"**

The strongest answer is not simply:

> "Implementing RAG."

The most challenging part was building **secure, durable document lifecycle management across multiple storage systems while maintaining retrieval isolation.**

A single document existed across multiple systems:

```text
Postgres
Qdrant
Storage
BM25/index cache
```

At the same time, the document could belong to either:

```text
LIBRARY
```

or:

```text
CONVERSATION
```

and access depended on:

```text
User
+
Conversation
+
Explicit retrieval intent
```

That meant authorization had to remain consistent across every retrieval path.

Then deletion introduced another distributed-systems problem:

```text
What happens if PostgreSQL succeeds
but Qdrant deletion fails?
```

The durable cleanup outbox solved this.

So the hardest part was really the combination of:

```text
Security
+
Distributed resource lifecycle
+
Consistency
+
Idempotence
+
Failure recovery
```

That is much more representative of real production engineering than simply implementing vector search.

---

# 34. The Most Valuable Debugging Lesson

One of the biggest lessons was:

> **Never assume that a passing happy path means the system is safe.**

Several bugs were discovered only when the system was intentionally attacked or stressed.

Examples:

```text
Missing document_scope
        ↓
Could accidentally become LIBRARY
```

```text
Model supplies foreign document ID
        ↓
Must still be rejected
```

```text
Cross-conversation chunk ID
        ↓
Must still be rejected
```

```text
50 concurrent requests
        ↓
Server deadlock
```

```text
Server crash during cleanup
        ↓
Cleanup must resume later
```

These scenarios changed how I think about testing.

---

# 35. What I Would Explain in an Interview

I would describe the project in five layers.

### Layer 1 — Product

> I built a production-oriented Hybrid RAG chatbot that lets users chat over their documents.

### Layer 2 — Retrieval

> It combines dense vector retrieval through Qdrant with sparse BM25 retrieval and uses hybrid ranking to improve recall and relevance.

### Layer 3 — Security

> I introduced explicit library and conversation document scopes and enforced them at the repository, retrieval, vector, sparse, API, and agent-tool layers.

### Layer 4 — Reliability

> Conversation deletion uses a durable cleanup-job pattern so PostgreSQL, Qdrant, and file storage can be cleaned up reliably even when external services fail.

### Layer 5 — Scalability

> I optimized Redis operations, removed an ingestion N+1 query pattern, bounded the in-memory index cache, optimized BM25 tokenization, and resolved a high-concurrency database-pool deadlock.

---

# 36. The "Architecture Evolution" Story

The most important story of the project is its evolution.

### Version 1

```text
Simple RAG
```

↓

### Version 2

```text
Hybrid RAG
Dense + Sparse
```

↓

### Version 3

```text
Production document management
```

↓

### Version 4

```text
Library vs Conversation scopes
```

↓

### Version 5

```text
Scope-aware retrieval
```

↓

### Version 6

```text
Secure agent tools
```

↓

### Version 7

```text
Durable distributed cleanup
```

↓

### Version 8

```text
Migration + verification
```

↓

### Version 9

```text
Scalability optimization
```

↓

### Version 10

```text
Load testing
```

↓

### Version 11

```text
Deployment
```

This evolution is itself an important interview story.

It demonstrates that the architecture was not blindly designed once and frozen.

It was **measured, challenged, corrected, and hardened**.

---

# 37. Engineering Decisions and Trade-offs

## Why synchronous SQLAlchemy?

Because replacing the entire persistence layer with async SQLAlchemy would have introduced substantial architectural risk late in the project.

The chosen approach preserved consistency and reduced the blast radius.

---

## Why Redis asyncio?

Redis operations were occurring naturally on async application paths, so moving those operations to the async Redis API was a lower-risk optimization.

---

## Why not Celery/Arq?

The project intentionally avoided introducing another distributed infrastructure dependency.

The cleanup worker remained in-process, while durability came from PostgreSQL cleanup jobs.

---

## Why PostgreSQL as the source of truth?

Because authorization and relational document ownership need a reliable transactional source of truth.

Qdrant and storage contain derived/external resources.

---

## Why explicit scope instead of frontend filtering?

Because frontend filtering is not a security boundary.

Authorization must happen server-side.

---

## Why reject missing scope metadata?

Because security systems should fail closed.

```text
Unknown permission
      ↓
DENY
```

not:

```text
Unknown permission
      ↓
ASSUME ALLOWED
```

---

# 38. What I Learned

## 1. RAG is more than embeddings

The difficult part of production RAG is often everything around retrieval:

```text
security
storage
lifecycle
evaluation
observability
failure handling
```

---

## 2. Authorization belongs close to the data

A UI check is not enough.

The repository and retrieval layers must independently enforce ownership and scope.

---

## 3. Distributed deletion is a real consistency problem

When one logical resource exists across PostgreSQL, Qdrant, and storage, deletion needs durability and idempotence.

---

## 4. Performance problems need measurement

The 50-user issue was not obvious from ordinary testing.

Load testing exposed it.

---

## 5. Security bugs can hide inside defaults

A line such as:

```python
value = metadata.get("scope") or "LIBRARY"
```

can become a serious authorization vulnerability.

---

## 6. Tests should include adversarial scenarios

Testing only:

```text
valid user
valid document
valid request
```

is insufficient.

You also need:

```text
wrong user
wrong conversation
malicious ID
missing metadata
partial failure
duplicate execution
high concurrency
```

---

# 39. Final Project State

The project concluded with:

```text
✓ Hybrid dense + sparse RAG
✓ Qdrant vector retrieval
✓ BM25 sparse retrieval
✓ Document ingestion
✓ Document scoping
✓ Library documents
✓ Conversation documents
✓ @documents retrieval intent
✓ Secure agent tools
✓ Cross-user isolation
✓ Cross-conversation isolation
✓ Durable cleanup jobs
✓ Idempotent cleanup
✓ Qdrant migration tooling
✓ Redis async optimization
✓ N+1 ingestion optimization
✓ Bounded LRU index cache
✓ BM25 pre-tokenization
✓ Database pool optimization
✓ Concurrent load testing
✓ 195/195 tests passing
✓ Live lifecycle verification
✓ Deployment completed
```

---

# 40. The One-Sentence Project Explanation

If I have only 20 seconds in an interview:

> **"I built and deployed a production-oriented Hybrid RAG chatbot using dense Qdrant retrieval and sparse BM25 retrieval, then hardened it with explicit library/conversation document scopes, multi-layer authorization, durable cross-system cleanup, agent-tool security, caching, and concurrency optimizations, ultimately validating the system with 195 automated tests and load testing that resolved a 50-concurrency deadlock."**

---

# 41. The 2-Minute Interview Version

> "The project started as a Hybrid RAG chatbot combining dense vector search through Qdrant with BM25 sparse retrieval. As I moved toward production readiness, the main challenges shifted from retrieval itself to security, lifecycle management, and scalability.
>
> One major architectural change was separating documents into persistent library documents and conversation-scoped documents. I introduced an explicit DocumentRetrievalScope and propagated it through the API, orchestrator, repository, Qdrant, BM25, and agent tools. This ensured that normal chat could only access conversation documents, while an explicit @documents intent could additionally access the user's library. Importantly, model-supplied document IDs were never trusted for authorization.
>
> Another difficult problem was conversation deletion because documents existed across PostgreSQL, Qdrant, physical storage, and caches. I implemented durable cleanup jobs so the PostgreSQL transaction records everything required for external cleanup before deleting the relational records. A background worker then performs idempotent Qdrant and storage deletion with retry and startup recovery.
>
> After security verification, I found and fixed several subtle issues, including permissive defaults for missing scope metadata and incomplete Qdrant filtering. The security suite was expanded and the project eventually reached 195 passing tests.
>
> Finally, I performed scalability work. I moved Redis operations to redis.asyncio, removed an ingestion N+1 query pattern, bounded the in-memory BM25 cache with LRU eviction, optimized tokenization, and addressed database connection-pool starvation. Load testing showed that the system previously failed completely at 50 concurrent users, while the optimized version handled 50 concurrent requests at 14.58 RPS with zero errors.
>
> After the final verification and live lifecycle tests, the application was deployed."

---

# 42. Final Reflection

The biggest transformation was not in the codebase.

It was in the engineering mindset.

The project started with:

```text
"How do I make RAG work?"
```

and ended with:

```text
"How do I make a RAG system secure,
durable, observable, testable,
recoverable, and scalable?"
```

That is the real journey of this project.
