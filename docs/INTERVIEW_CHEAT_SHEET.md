# FusionRAG: The Golden Architectural Cheat Sheet
### High-Density Executive Reference & Systems Compass

> **How to use this Cheat Sheet:**
> This 1-page document distills the entire 18,000-line FusionRAG system architecture into its essential formulas, invariants, memory layouts, and triage runbooks. Review this before interviews or architecture reviews to keep the physical mechanics and system boundaries front-of-mind.

---

## 1. Golden Constants & Mathematical Invariants

| Parameter / Heuristic | Production Value | Architectural Rationale & Formula |
| :--- | :--- | :--- |
| **RRF Smoothing Constant ($k$)** | **`60`** | Reciprocal Rank Fusion: $\text{RRF}(d) = \sum_{c} \frac{w_c}{k + r_c(d)}$. $k=60$ prevents top-ranked outliers in one channel (sparse or dense) from monopolizing the merged rank. |
| **MMR Diversity Factor ($\lambda$)** | **`0.5`** | Maximal Marginal Relevance: $\text{MMR} = \operatorname{argmax}_{d_i \in R \setminus S} \left[ \lambda \cdot \text{Sim}_1(d_i, q) - (1 - \lambda) \max_{d_j \in S} \text{Sim}_2(d_i, d_j) \right]$. $\lambda=0.5$ balances relevance and novelty. |
| **Model Routing Complexity Threshold** | **`0.60`** | `ComplexityModelRouter`: Query score $\ge 0.60 \implies$ `HEAVY` (`gemini-2.5-flash`); $< 0.60 \implies$ `LIGHT` (`gemini-3.5-flash-lite`). Zero API overhead ($<0.1\text{ms}$). |
| **Context Escalation Ceiling** | **`4,000` tokens** | If retrieved context $> 4,000$ tokens, query complexity score receives $+0.15$ boost, escalating to `HEAVY` tier to prevent attention degradation. |
| **Database Pool Configuration** | **`size=20, max_overflow=10`** | Tuned to exceed AnyIO worker concurrency to prevent connection pool starvation deadlocks under heavy load. |
| **PgBouncer Statement Cache** | **`statement_cache_size=0`** | In `backend/app/db/session.py`, driver-level prepared statements are disabled to avoid `prepared statement "P1" does not exist` errors in transaction pooling. |
| **Argon2id Password Hasher** | **$m=65536, t=3, p=4$** | NIST SP 800-63B compliant: 64 MB RAM, 3 iterations, 4 parallel threads. Resists GPU brute-force and side-channel timing attacks. |
| **Token Refresh Window** | **`15m` access / `7d` refresh** | Single-use rotated HTTP-only refresh cookies. Any token replay triggers immediate family revocation across all active sessions. |
| **RAG Cache Paced Replayer** | **`5ms` event pacing** | Replays cached L3 answers at 5ms token intervals via synthetic SSE generator to preserve frontend typewriter animations and UX continuity. |
| **AST Exponent DOS Cap** | **`base <= 10000, exp <= 15`** | In `SafeCalculator`, rejects $a^b$ if values exceed bounds, mathematically preventing CPU/RAM denial-of-service in sandboxed math. |

---

## 2. Dynamic Complexity Model Routing Scoring Engine

```
                                  Incoming Query Text
                                           │
                        DeterministicQueryClassifier (Regex)
                                           │
                      ┌────────────────────┴───────────────────┐
                      ▼                                        ▼
             Base Complexity Mapping                  Modifier Boost Rules
        CONVERSATIONAL: 0.10                     requires_decomposition: max(score, 0.85)
        FACTUAL / AMBIGUOUS: 0.30                has_multiple_evidence_targets: max(score, 0.80)
        EXPLANATION: 0.55                        Compound regex ('and what/who...'): max(score, 0.75)
        NUMERICAL: 0.70                          Question marks count > 1: max(score, 0.80)
        TABLE / GRAPH / COMPARISON: 0.85         Query length > 350 chars: min(1.0, score + 0.15)
        MULTI_DOCUMENT: 0.90                     Context tokens > 4000: min(1.0, score + 0.15)
        MULTI_HOP: 0.95                          
                      └────────────────────┬───────────────────┘
                                           │
                              Final Complexity Score
                                           │
                      ┌────────────────────┴───────────────────┐
                      ▼                                        ▼
               Score < 0.60                             Score ≥ 0.60
            ┌──────────────────┐                     ┌──────────────────┐
            │    LIGHT TIER    │                     │    HEAVY TIER    │
            │gemini-3.5-flash-lite                   │ gemini-2.5-flash │
            │Sub-second factual│                     │Multi-hop, Tables │
            └──────────────────┘                     └──────────────────┘
```

---

## 3. The "Junior vs. Staff" Interview Answer Compass

When answering architectural interview questions, follow this mental model to hit Staff/Principal signals:

| Topic | 1-Year Junior Answer (The Feature) | Senior Answer (The Mechanism) | Staff / Principal Answer (The Physics & Failure Modes) |
| :--- | :--- | :--- | :--- |
| **PostgreSQL MVCC** | *"It keeps multiple versions so reads don't block writes."* | *"Updates insert new rows with `xmin`/`xmax`. Reads check snapshots of active transactions."* | *"8 KB disk pages use line pointers. Updates generate duplicate index entries unless HOT (Heap-Only Tuple) applies on the same page. 32-bit `xmin` requires periodic autovacuum freezing to prevent transaction wraparound data loss."* |
| **Redis Architecture** | *"Redis is an in-memory key-value store that runs on a single thread."* | *"It uses an epoll event loop (`ae.c`) so it can handle 100k req/s without lock contention."* | *"The reactor pattern multiplexes sockets. Redis 6/7 offloads socket I/O and `UNLINK` to background threads. $O(N)$ operations (`KEYS *`) stall the single reactor; `SCAN` must be used. AOF `everysec` risks 1s data loss on crash."* |
| **Qdrant Vector Search** | *"It finds similar chunks using cosine similarity vectors."* | *"It builds an HNSW graph to find approximate nearest neighbors in logarithmic time."* | *"Multi-layer graph skip-list with `M` connections and `ef_search` beam width. Single-stage payload filtering walks the graph while masking disqualified vertices; naive pre-filtering breaks HNSW connectivity."* |
| **Model Routing** | *"We send easy questions to Flash-Lite and hard ones to Flash."* | *"A classifier inspects query keywords and token counts to pick the model."* | *"Sub-millisecond zero-API router avoids auxiliary LLM latency ($<0.1\text{ms}$). Maps query types to base scores, applies boost modifiers, and injects `effective_model` into `RAGCacheService` keys to prevent cross-tier cache contamination."* |
| **Distributed Deletion** | *"When a document is deleted, we delete it from Postgres, S3, and Qdrant."* | *"We use background tasks so the HTTP delete endpoint returns immediately."* | *"Dual-write hazard: if S3 fails after DB commit, orphans remain. FusionRAG uses the Transactional Outbox pattern (`durable_cleanup_jobs`) committed atomically with relational rows, processed idempotently by a reaper worker."* |

---

## 4. Multi-Tier RAG Cache Hierarchy

```
[Incoming Query] 
   │
   ├──> L1: In-Memory Index Cache (LRU, 500 users) 
   │         └── Checks if user has ANY indexed chunks (avoids Qdrant calls for empty KBs)
   │
   ├──> L2: Redis Context Cache (TTL: 30m)
   │         └── Caches cross-encoder reranked context payloads by (doc_versions_hash, query_hash)
   │
   └──> L3: RAG Response Cache (TTL: 1h)
             ├── Active-Version Fingerprint: hash(doc_id, active_version, effective_model, query)
             ├── Envelope Encryption: AES-256-GCM using User Data Encryption Key (DEK)
             ├── Crypto-Shredding: Deleting user DEK shreds all Redis cache dumps instantly
             └── Fast-Replay Engine: Paced SSE replayer at 5ms intervals preserves typewriter UX
```

---

## 5. Multi-Agent DAG Orchestration Engine

1. **MasterAgent Planning**: Generates an `ExecutionPlan` with typed `TaskNodes`.
2. **Kahn's Algorithm Validation**:
   - Computes in-degrees for all task nodes.
   - Detects dependency cycles ($O(V + E)$). Rejects circular dependencies immediately.
3. **Topological Wave Concurrency**:
   - **Wave 0 (Independent)**: `ResearchAgent`, `WebSearchAgent`, `DocumentAgent`, `VisionAgent`, `GraphAgent` run in parallel via `asyncio.gather()`.
   - **Wave 1 (Dependent)**: `TableAgent` and `AnalysisAgent` execute after consuming Wave 0 outputs.
4. **Adaptive Replanning**: `ResultEvaluator` grades evidence on relevance, completeness, and contradictions. If insufficient, replans up to 2 times without re-executing already-successful nodes.

---

## 6. Top 8 Production Incident Triage Cheatsheet

| Incident | First Telemetry Check | Immediate Mitigation | Permanent Fix |
| :--- | :--- | :--- | :--- |
| **PostgreSQL Pool Deadlock** | `SELECT count(*), state FROM pg_stat_activity GROUP BY state;` | `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';` | Set `connect_args={"statement_cache_size": 0}`, enforce async generator session context (`async with get_db()`). |
| **Cross-Tenant Vector Leak** | OTel span `qdrant.search` payload filter attribute | Roll back deployment; verify payload filter: `must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]` | Add CI regression test with adversarial tenant cross-queries. |
| **Upstream 429 LLM Outage** | Prometheus `GEMINI_429_TOTAL` counter | Trigger failover proxy: traffic automatically shifts from `GEMINI_API_KEY` to `GEMINI_FALLBACK_API_KEY`. | Multi-key workload isolation (LLM, Planner, Fallback on separate quotas). |
| **Zip-Bomb Upload DoS** | API pod CPU/Memory spikes on `POST /upload` | Terminate worker pod; ClamAV socket drops stream. | `MagicByteValidator` enforces strict decompression ratio limit ($< 100\times$, max 25 MB). |
| **JWT Replay Attack** | Security log `REFRESH_TOKEN_REUSE_DETECTED` | Invalidate all active sessions for `user_id`: `DELETE FROM refresh_sessions WHERE user_id = :uid;` | Enforce single-use token rotation with immediate family revocation. |
| **Stale Vector Syndrome** | Chunks returned for deleted document ID | Purge orphans: `qdrant.delete(points_selector=Filter(must_not=[MatchAny(valid_doc_ids)]))` | Verify `DurableCleanupJob` outbox worker execution. |
| **Alembic Lock Contention** | `SELECT * FROM pg_locks WHERE NOT granted;` | Kill blocking DDL query; inspect table lock level. | Set `lock_timeout = '5s'`; use `CREATE INDEX CONCURRENTLY`. |
| **Model Routing Misclassification** | OTel span `rag.model_routing` attribute `llm.routing_reason` | Adjust `MODEL_ROUTING_MIN_COMPLEXITY_THRESHOLD` via environment variable without code deployment. | Add domain-specific regex patterns to `DeterministicQueryClassifier`. |
