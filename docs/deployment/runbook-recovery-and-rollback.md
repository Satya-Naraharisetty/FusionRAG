# Production Recovery & Rollback Runbook

This operational runbook provides concise, actionable procedures for rolling back failed deployments and recovering system state across the Fusion RAG production architecture (Combination H).

---

## 1. System Topology & State Classification

Understanding where authoritative vs. derived state resides determines the appropriate recovery action:

```text
GitHub (main branch)
   │
   ├── Vercel (Frontend React SPA)
   │
   └── Render (Backend FastAPI ASGI Service)
           │
           ├── Supabase PostgreSQL  → [AUTHORITATIVE STATE]
           │                         (Users, Documents, Chunks, Messages, Settings)
           │
           ├── Qdrant Cloud         → [DERIVED STATE]
           │                         (Vector embeddings generated from Chunk records)
           │
           ├── Upstash Redis        → [EPHEMERAL / QUEUE STATE]
           │                         (Redis Streams, Rate limiting, Token blacklists)
           │
           ├── Jina AI              → Stateless Embeddings & Cross-Encoder Reranker
           ├── Google Gemini        → Stateless LLM Generation (Dynamic Model Routing: Flash-Lite / Flash)
           └── Resend               → Transactional Email
```

### State Guarantees
* **PostgreSQL (Supabase)**: Authoritative source of truth. All documents, user accounts, conversation histories, and chunk texts live here.
* **Qdrant Cloud**: Derived vector index. If Qdrant is wiped or corrupted, it can be completely regenerated from the authoritative chunks in PostgreSQL.
* **Upstash Redis**: Ephemeral queue and caching layer. If Redis is flushed, active jobs in progress are re-enqueued by the `DurableIngestionReaper`, and rate limit counters reset to zero.

---

## 2. Frontend Rollback (Vercel)

Vercel provides instantaneous atomic rollbacks without requiring code rebuilding.

### Procedure
1. Navigate to the project dashboard on [vercel.com](https://vercel.com).
2. Click the **Deployments** tab.
3. Locate the previous known-good deployment (look for green build status prior to the incident).
4. Click the three dots menu (`...`) on the target deployment and select **Promote to Production** (or **Rollback**).
5. Vercel instantly routes 100% of live traffic to the target build within seconds.

### Post-Rollback Verification
* Open the production URL in an incognito window.
* Verify login and navigation render without console bundle errors.

---

## 3. Backend Rollback (Render)

### Application Rollback vs. Database Migration Rollback

> [!IMPORTANT]
> **Application rollback** and **database migration rollback** are completely separate operations:
> - **Application Rollback (Standard)**: Reverting the running container to a previous code commit. This is safe and non-destructive if the database schema is backward-compatible.
> - **Database Migration Rollback (Exceptional)**: Running `alembic downgrade`. This is a high-risk operation that can destroy newly written columns or data.

### Standard Application Rollback Procedure
1. Navigate to your backend Web Service on [render.com](https://render.com).
2. Go to the **Events** or **Deploys** tab.
3. In the list of past deploys, locate the last stable deploy commit.
4. Click **Rollback** (or git revert the commit in `main` and push to trigger an automated rebuild).
5. Monitor the build logs to confirm successful container start (`uvicorn app.main:app`).

---

## 4. Database Recovery (Supabase PostgreSQL)

### Backup Policies
* **Automated Backups**: Supabase performs standard automated daily backups of the PostgreSQL database.
* **Logical Dumps**: Custom manual backups can be created at any time using `pg_dump`:
  ```bash
  pg_dump "postgresql://postgres.[username]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres" \
    --clean --if-exists --no-owner --no-privileges -F p -f backup_$(date +%Y%m%d).sql
  ```

### Recovery from Backup
If a catastrophic data corruption occurs:
1. In the Supabase Dashboard, navigate to **Database** $\rightarrow$ **Backups**.
2. Select the daily backup restore point.
3. Confirm restore (note that queries during restore will pause).
4. Verify database connectivity:
   ```bash
   uv run python -c "from app.db.session import engine; import asyncio; asyncio.run(engine.connect())"
   ```

---

## 5. Qdrant Vector Recovery (Derived State Rebuild)

Because Qdrant vectors are derived from PostgreSQL document chunks, a corrupted or out-of-sync vector collection can be restored directly from PostgreSQL.

### Rebuild Mechanism
1. **Per-Document Reprocessing**:
   To reprocess a single failed or out-of-sync document, trigger the reprocessing endpoint:
   ```http
   POST /api/v1/documents/{document_id}/reprocess
   Authorization: Bearer <user_access_token>
   ```
   Or regenerate embeddings directly:
   ```http
   POST /api/v1/documents/{document_id}/embeddings/regenerate
   Authorization: Bearer <user_access_token>
   ```
2. **Worker Ingestion Pipeline**:
   The `reprocess_document` endpoint marks the document status as `QUEUED` and publishes a processing task to the Redis Stream. The background worker cleans, chunks, batches embeddings via Jina, and upserts vectors directly into Qdrant.
3. **Stalled Job Recovery**:
   The `DurableIngestionReaper` background task automatically scans for documents stuck in `PROCESSING` state past the configured timeout window and reclaims or re-queues them.

---

## 6. Redis Recovery (Queue & Ephemeral State)

If the Upstash Redis instance is cleared or restarted:
1. **Impact**:
   - Active rate limiting windows and temporary failed-login lockouts are reset.
   - Any in-flight Redis Stream messages not yet acknowledged are lost.
2. **Recovery Procedure**:
   - The PostgreSQL state remains untouched.
   - Documents that were queued during the Redis restart will be detected as uncompleted by the `DurableIngestionReaper` and can be re-triggered via `/reprocess`.
   - Background tasks resume normal operation automatically as new requests arrive.

---

## 7. Failed Migration Scenario Decision Tree

```text
               Deployment or Migration Fails
                            │
                            ▼
               Inspect Render Application Logs
                            │
                            ▼
              Did the schema migration succeed?
                            │
            ┌───────────────┴───────────────┐
            │                               │
           YES                              NO
            │                               │
            ▼                               ▼
Is schema backward-compatible?     Fix migration syntax or
            │                      connection issue in code;
     ┌──────┴──────┐               re-deploy commit to main
     │             │
    YES            NO
     │             │
     ▼             ▼
Safe to roll back   CRITICAL: Do NOT blindly run 'alembic downgrade -1'.
application code    Inspect the migration file:
only. DB schema    - If additive (new tables/indexes): Leave DB as-is;
remains on head.     rollback application code.
                   - If destructive (column drops): Restore from Supabase
                     backup or apply a forward-fixing migration.
```

---

## 8. Post-Recovery Verification Checklist

After any recovery or rollback incident, verify system health using this step-by-step checklist:

| Check | Target / Endpoint | Expected Response |
|---|---|---|
| **1. Liveness Probe** | `GET /api/v1/health/liveness` | `HTTP 200 {"status": "alive"}` |
| **2. Readiness Probe** | `GET /api/v1/health/readiness` | `HTTP 200 {"status": "healthy", "services": {"postgres": "connected", "vector_db": "connected", "redis": "connected"}}` |
| **3. Frontend UI** | `GET https://<your-app>.vercel.app` | Login page loads without JavaScript runtime errors |
| **4. Auth Flow** | `POST /api/v1/auth/login` | Returns valid JWT access token and session cookie |
| **5. Document Retrieval** | `GET /api/v1/documents` | Returns user's uploaded document library list |
| **6. End-to-End RAG Chat** | `POST /api/v1/chat/conversations/{id}/messages` with `@documents` | Streams response chunks via SSE with citations |

---

## 9. Emergency Model Routing Kill-Switch & Quota Load Shedding

If upstream Google Gemini `gemini-2.5-flash` encounters HTTP 429 quota exhaustion or regional degradation:

1. **Option A: Emergency Kill-Switch (Revert to Single-Model Mode)**:
   Disable dynamic complexity routing in Render or Kubernetes dashboard:
   ```bash
   # Reverts all requests to GEMINI_CHAT_MODEL (gemini-3.5-flash-lite)
   ENABLE_DYNAMIC_MODEL_ROUTING=False
   ```
2. **Option B: Runtime Load Shedding (Raise Threshold)**:
   Divert 85%+ of complex queries back to the lightweight model without restarting the application:
   ```bash
   MODEL_ROUTING_MIN_COMPLEXITY_THRESHOLD=0.95
   ```
3. **Verification**:
   Inspect OpenTelemetry Jaeger traces under `rag.model_routing` or server logs:
   ```text
   ModelRouter: routed '...' -> gemini-3.5-flash-lite (LIGHT, reason=routing_disabled)
   ```
