# Complete Free-Tier Deployment Guide ($0 / Month)

This guide walks you through deploying the Hybrid RAG system (Combination H) for **$0 / month** using free-tier services.

---

## 1. Free Services & Environment Variable Map

| Component | Provider | Setup Location | Environment Variables |
|---|---|---|---|
| **Database** | **Supabase** | [supabase.com](https://supabase.com) (Database $\rightarrow$ Connection string $\rightarrow$ URI Transaction pooler `6543`) | `DATABASE_URL=postgresql://postgres.[username]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?pgbouncer=true` |
| **Vector DB** | **Qdrant Cloud** | [cloud.qdrant.io](https://cloud.qdrant.io) (Free 1GB Cluster $\rightarrow$ API Keys) | `QDRANT_URL=https://[cluster-id].[region].qdrant.io:6333`<br>`QDRANT_API_KEY=[your-qdrant-api-key]`<br>`QDRANT_COLLECTION=documents` |
| **Redis** | **Upstash** | [upstash.com](https://console.upstash.com) (Create Redis Database $\rightarrow$ REST / Connection URL) | `REDIS_URL=rediss://default:[password]@[endpoint].upstash.io:6379` |
| **Embeddings & Reranker** | **Jina AI** | [jina.ai](https://jina.ai) (API Keys) | `EMBEDDING_PROVIDER=jina`<br>`EMBEDDING_MODEL=jina-embeddings-v3`<br>`EMBEDDING_DIMENSION=768`<br>`ENABLE_RERANKER=True`<br>`RERANKER_PROVIDER=jina`<br>`RERANKER_MODEL=jina-reranker-v2-base-multilingual`<br>`JINA_API_KEY=[your-jina-api-key]` |
| **LLM** | **Google AI Studio** | [aistudio.google.com](https://aistudio.google.com) (Get API Key) | `LLM_PROVIDER=gemini`<br>`GEMINI_CHAT_MODEL=gemini-3.5-flash-lite`<br>`GEMINI_API_KEY=[your-gemini-api-key]` |
| **Security Keys** | **Generated Secure Hex** | `openssl rand -hex 32` | `JWT_SECRET=bca69475fe88250acaaf884bbb0a73b3ebfd1dd5747628865dbe9508803c9467`<br>`ENCRYPTION_MASTER_KEY=a2f40610c1b6e282cda1a80c0316d6ee50d02b9a30d5ce37ae641d8dc5c41296` |

---

## 2. Backend Deployment (Render.com — 100% Free)

Render provides a free Web Service tier suitable for FastAPI:

### Step 1: Create a Render Web Service
1. Log in to [render.com](https://render.com) and click **New +** $\rightarrow$ **Web Service**.
2. Connect your GitHub repository.
3. Configure the service:
   - **Name**: `hybrid-rag-backend`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install uv && uv sync --frozen --no-dev
     ```
   - **Start Command**:
     ```bash
     uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: `Free`

### Step 2: Set Environment Variables in Render Dashboard
Go to the **Environment** tab in your Render Web Service and add:

```dotenv
ENV=production
PROJECT_NAME=Hybrid RAG Chatbot
API_V1_STR=/api/v1

# Supabase PostgreSQL (Transaction Pooler Port 6543)
DATABASE_URL=postgresql://postgres.[username]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?pgbouncer=true

# Upstash Redis
REDIS_URL=rediss://default:[password]@[endpoint].upstash.io:6379

# Qdrant Cloud
QDRANT_URL=https://[cluster-id].[region].qdrant.io:6333
QDRANT_API_KEY=[your-qdrant-api-key]
QDRANT_COLLECTION=documents

# Jina AI
EMBEDDING_PROVIDER=jina
EMBEDDING_MODEL=jina-embeddings-v3
EMBEDDING_DIMENSION=768
ENABLE_RERANKER=True
RERANKER_PROVIDER=jina
RERANKER_MODEL=jina-reranker-v2-base-multilingual
RERANK_TOP_K=5
JINA_API_KEY=[your-jina-api-key]

# Google Gemini
LLM_PROVIDER=gemini
GEMINI_CHAT_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=[your-gemini-api-key]

# Storage
STORAGE_PROVIDER=database

# Security (32+ character secrets)
JWT_SECRET=[generated-secret-from-openssl]
ENCRYPTION_MASTER_KEY=[generated-secret-from-openssl]
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=True
COOKIE_SAMESITE=none

# CORS Configuration
FRONTEND_URL=https://[your-frontend-app].vercel.app
BACKEND_CORS_ORIGINS=https://[your-frontend-app].vercel.app
```

### Step 3: Run Database Migrations
Before the application starts serving requests, run the initial Alembic migration against your Supabase database.
You can run this locally from your machine pointing to your Supabase `DATABASE_URL`:

```bash
cd backend
DATABASE_URL="postgresql://postgres.[username]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?pgbouncer=true" uv run alembic upgrade head
```

---

## 3. Frontend Deployment (Vercel — 100% Free)

Vercel is the optimal free hosting platform for the frontend.

### Step 1: Deploy to Vercel
1. Log in to [vercel.com](https://vercel.com) and click **Add New...** $\rightarrow$ **Project**.
2. Import your GitHub repository.
3. Set **Root Directory** to `frontend`.
4. In **Environment Variables**, add:
   ```dotenv
   VITE_API_BASE_URL=https://hybrid-rag-backend.onrender.com
   ```
   *(or `NEXT_PUBLIC_API_URL` if using Next.js)*.
5. Click **Deploy**.

---

## 4. Post-Deployment Smoke Test & Verification

Once both services are deployed:

1. **Verify Backend Health**:
   ```bash
   curl -i https://[your-render-backend].onrender.com/health
   ```
   Expected response:
   ```json
   {"status": "ok"}
   ```

2. **Verify Metrics Endpoint**:
   ```bash
   curl -i https://[your-render-backend].onrender.com/api/v1/observability/metrics
   ```
   Expected response: Prometheus metrics with HTTP 200.

3. **Verify Full Application Flow**:
   - Open your Vercel URL (`https://[your-app].vercel.app`).
   - Register a new user account.
   - Upload a test PDF or Markdown document.
   - Ask a question in the chat interface and verify that citations and retrieved context stream smoothly.
