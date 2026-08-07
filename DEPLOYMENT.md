# Deployment Manual - Hybrid RAG Chatbot

This manual provides setup, operation, backup, and release guides for deploying the **Hybrid RAG Chatbot** to cloud serverless hosting and managed backing services: Vercel, Supabase, Upstash Redis, and Qdrant Cloud.

---

## 1. Supported Software Versions & Environments

*   **Hosting Platform**: Vercel (Python 3.12+ Serverless Functions & Node.js 18/20+ Static build)
*   **PostgreSQL**: Supabase Managed Database (PostgreSQL 16.x)
*   **Redis**: Upstash Serverless Redis (Redis 7.2.x compatible)
*   **Vector Database**: Qdrant Cloud Cluster (Qdrant 1.9.x compatible)
*   **Python runtime**: `>=3.12` (with packages installed via `requirements.txt` generated from `pyproject.toml`)
*   **NodeJS runtime**: `18.x` or `20.x` (for frontend build)

---

## 2. Production Environment Configurations

Environment variables are configured in your Vercel project dashboard. Populate these keys before deploying:

### Backend Environment Variables
| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `ENV` | Environment identifier | `production` |
| `DATABASE_URL` | Supabase Connection Pooler URI (port 6543) | `postgresql://postgres.xxx:password@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?pgbouncer=true` |
| `REDIS_URL` | Upstash Redis connection string | `rediss://default:password@endpoint.upstash.io:port` |
| `QDRANT_URL` | Qdrant Cloud cluster endpoint | `https://xxxxxx.gcp.qdrant.io:6333` |
| `QDRANT_API_KEY` | Qdrant API authorization key | `(Your Qdrant API Key)` |
| `JWT_SECRET` | 32+ bytes signing key for JWT tokens | `(Your Generated Secret Key)` |
| `GEMINI_API_KEY` | Primary LLM Provider API Key | `AIzaSy...` |
| `OPENAI_API_KEY` | Backup LLM & Embeddings API Key (optional) | `sk-proj-...` |
| `STORAGE_PROVIDER` | Ingestion storage engine (`database` or `s3`) | `database` |
| `COOKIE_SECURE` | Forces secure HTTPS-only session cookies | `True` |
| `COOKIE_SAMESITE` | Cookie cross-site policy | `none` |

### Frontend Environment Variables
| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `VITE_API_URL` | Backend Vercel deployment URL | `https://your-backend-vercel-url.vercel.app` |

---

## 3. Backing Services Setup Guide

### A. Database Setup (Supabase)
1. Sign up/log in to [Supabase](https://supabase.com/).
2. Create a new project.
3. Retrieve your **Transaction Connection Pooler string** from **Project Settings > Database > Connection strings** (select `URI` and ensure it uses port `6543` with `pgbouncer=true`).
4. Set this URL as your `DATABASE_URL` in your Vercel backend environment variables.

### B. Cache Setup (Upstash Redis)
1. Sign up/log in to [Upstash](https://upstash.com/).
2. Create a new Redis database (enable TLS/SSL).
3. Copy the **Redis URL** under the **Node / Python** client instructions. It should look like:
   `rediss://default:password@endpoint.upstash.io:port`
4. Set this as your `REDIS_URL` in your Vercel backend environment variables.

### C. Vector DB Setup (Qdrant Cloud)
1. Sign up/log in to [Qdrant Cloud](https://cloud.qdrant.io/).
2. Create a new cluster.
3. Retrieve your **Endpoint URL** (e.g., `https://xxxxxx.gcp.qdrant.io:6333`) and generate an **API Key**.
4. Set these as `QDRANT_URL` and `QDRANT_API_KEY` in Vercel.
5. Create the required collection (named `documents` or matching your `VECTOR_COLLECTION_NAME` config):
   - You can create it via Qdrant Cloud Console or run a curl command locally:
     ```bash
     curl -X PUT "https://xxxxxx.gcp.qdrant.io:6333/collections/documents" \
       -H "api-key: your-api-key" \
       -H "Content-Type: application/json" \
       -d '{"vectors": {"size": 3072, "distance": "Cosine"}}'
     ```
     *(Note: Update the vector size if using an embedding model other than `gemini-embedding-2` which has `3072` dimensions)*

---

## 4. Database Migrations

Apply database schema migrations to the Supabase database using Alembic from your local development machine:
```bash
ENV=production DATABASE_URL="your-supabase-connection-uri" alembic upgrade head
```

---

## 5. Vercel Serverless Deployment

Vercel supports deploying the monorepo by setting up two separate projects pointing to the same git repository.

### A. Backend API Deployment
1. Connect your git repository to Vercel and create a new project.
2. Select the repository and click **Edit** next to **Root Directory**. Set it to `backend`.
3. Set the **Framework Preset** to **Other** (Vercel automatically detects the Python runtime from the `api/` folder and `requirements.txt`).
4. Configure the **Environment Variables** in the project settings (see Section 2).
5. Click **Deploy**. Vercel will build the API and provide a deployment URL (e.g., `https://hybrid-rag-backend.vercel.app`).

### B. Frontend Client Deployment
1. Create a second project on Vercel pointing to the same git repository.
2. Set the **Root Directory** to `frontend`.
3. Vercel will automatically detect **Vite** as the framework.
4. Update the `frontend/vercel.json` file to route `/api/*` to your newly deployed backend:
   ```json
   {
     "version": 2,
     "rewrites": [
       {
         "source": "/api/:path*",
         "destination": "https://hybrid-rag-backend.vercel.app/api/:path*"
       },
       {
         "source": "/(.*)",
         "destination": "/index.html"
       }
     ]
   }
   ```
5. Configure the **Environment Variables** for the frontend:
   - `VITE_API_URL`: `https://hybrid-rag-backend.vercel.app`
6. Click **Deploy**. Vercel will build the React SPA and provide your application URL (e.g., `https://hybrid-rag-chat.vercel.app`).

---

## 6. Programmatic Backups & Restores

### A. PostgreSQL Database (Supabase)
Since the database is hosted on Supabase, backups can be scheduled natively via the Supabase dashboard (automatic daily backups).
For manual backups/restores, use the standard PostgreSQL CLI tools locally:
*   **Backup**:
    ```bash
    pg_dump -h aws-0-ap-south-1.pooler.supabase.com -U postgres.xxx -d postgres -F c -b -v -f supabase_backup.dump
    ```
*   **Restore**:
    ```bash
    pg_restore -h aws-0-ap-south-1.pooler.supabase.com -U postgres.xxx -d postgres -v supabase_backup.dump
    ```

### B. Qdrant Vector Indices
Use Qdrant's HTTP Snapshots API to backup your collections:
*   **Create Snapshot**:
    ```bash
    curl -X POST "https://xxxxxx.gcp.qdrant.io:6333/collections/documents/snapshots" -H "api-key: your-api-key"
    ```
*   **Download Snapshot**:
    Download the created snapshot from your Qdrant Cloud dashboard, or use `wget`/`curl` with the snapshot URL returned by the create endpoint.

---

## 7. Production Release Checklist

Prior to launching user traffic, confirm that all items are checked:
*   [ ] **Healthchecks**: Liveness (`/health/liveness`) and Readiness (`/health/readiness`) endpoints return HTTP 200.
*   [ ] **DB Migrations**: Alembic version matches the latest script head.
*   [ ] **Deep Health**: `/health/deep` returns all backing systems (Database, Redis, Qdrant) as "healthy".
*   [ ] **Smoke Test**: `python backend/scripts/smoke_test.py --full` succeeds without warnings (run with environment variables set).
*   [ ] **HTTPS / TLS**: Custom domains are active on Vercel with valid SSL certificates.
*   [ ] **Secrets Hardening**: `COOKIE_SECURE` is set to `True` and API keys are stored securely as secret environment variables.
