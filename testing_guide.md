# Local Testing and Development Guide

This guide describes how to run, test (both automated and manual), and develop the **Hybrid RAG Chatbot** application locally.

---

## 1. Start the Services via Docker Compose

The project includes containerized configurations for all backend services (FastAPI Backend, PostgreSQL, Redis, and Qdrant). A [docker-compose.yml](file:///d:/fun/hybrid_rag/docker-compose.yml) has been created at the root of the project to orchestrate them.

1. Ensure **Docker Desktop** (or Docker Engine) is running on your machine.
2. Spin up all backend services in the background by running the following command from the root of the repository (`d:\fun\hybrid_rag`):
   ```bash
   docker compose up -d
   ```

   *Note: This command builds the backend Docker image, starts the databases, automatically applies Alembic migrations, and boots the FastAPI server on `http://localhost:8000`.*
3. To stop and clean up the services when you are done, run:
   ```bash
   docker compose down
   ```

---

## 2. Environment Configuration for Local Manual Testing

By default, the `.env` file at the root of the project is configured to use cloud-hosted databases (Supabase, Upstash, Qdrant Cloud). To test the application fully against your **local Docker containers**, update your `.env` file as follows:

### A. Redirect Databases to Local Containers

Modify your `.env` file to swap the remote connection strings for the local container ports:

```properties
# ==============================================================================
# Relational Database (PostgreSQL)
# ==============================================================================
# Comment out or clear the remote DATABASE_URL:
DATABASE_URL=""

# Uncomment the local PostgreSQL credentials:
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=hybrid_rag
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# ==============================================================================
# Cache (Redis)
# ==============================================================================
# Comment out or clear the remote REDIS_URL:
REDIS_URL=""

# Uncomment the local Redis configurations:
REDIS_HOST=localhost
REDIS_PORT=6379

# ==============================================================================
# Vector DB (Qdrant)
# ==============================================================================
# Comment out or clear the remote QDRANT_URL and API Key:
QDRANT_URL=""
QDRANT_API_KEY=""

# Uncomment the local Qdrant configurations:
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=documents
```

### B. Configure Real LLM API Keys

To process documents and generate chatbot responses, you must supply active API keys for the LLM providers. Replace the default `mock_key` values with your real keys:

```properties
# LLM Providers Configuration
LLM_PROVIDER=gemini
LLM_PROVIDER_BACKUP=openai
GEMINI_API_KEY=your_actual_gemini_api_key_here
OPENAI_API_KEY=your_actual_openai_api_key_here
```

---

## 3. Applying Database Migrations Locally

> [!NOTE]
> If you are running the backend inside Docker via `docker compose up -d`, Alembic schema migrations are applied automatically on startup of the backend container.

If you are developing/running the backend locally outside of Docker, you must apply the Alembic schema migrations manually before starting the application:

1. Open a terminal at the repository root and activate the virtual environment:
   ```powershell
   & .venv/Scripts/Activate.ps1
   ```
2. Navigate to the `backend` directory and run the migrations:
   ```powershell
   cd backend
   alembic upgrade head
   ```

This will create the `users`, `refresh_sessions`, `documents`, `document_chunks`, and other necessary tables.

---

## 4. Running the Development Servers

With the backend services running (either via Docker Compose or manually), you can run the frontend to perform manual tests in your browser.

### A. Start the Backend API Server (Optional - if not using Docker)

> [!NOTE]
> If you started the backend service via `docker compose up -d`, the Backend API is already running on `http://localhost:8000` (and `http://127.0.0.1:8000`). You can skip this step and proceed to starting the frontend.

If you want to run/debug the backend locally outside of Docker:

1. Stop the docker backend container first:
   ```bash
   docker compose stop backend
   ```
2. Start the backend server in your backend terminal (with the `.venv` activated):
   ```powershell
   # Set the environment variable to development
   $env:ENV="development"

   # Run Uvicorn pointing to the app module
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

Verify the server is up and connected to databases by visiting:
[http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### B. Start the Frontend UI Server

In a new terminal:

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 5. Performing Manual Verification

Once both servers are running, walk through these steps to manually test the app:

1. **User Authentication**:
   - Go to [http://localhost:5173](http://localhost:5173) and sign up (Register) with a test email and password.
   - Verify that you are logged in and a session cookie/token is successfully created.
2. **Document Ingestion**:
   - Create a collection and upload a test document (e.g., a `.txt` or `.pdf` file).
   - Check that the UI updates the document status from `Queued` -> `Processing` -> `Completed`.
3. **Conversational QA & Citations**:
   - Type a question that is relevant to the uploaded document.
   - Verify that:
     - The response streams in real-time.
     - The answer contains inline citations referencing the document.
     - The citation sidebar displays source previews and metadata.

---

## 6. Running Automated Tests

To ensure code stability during changes, you can run the automated tests at any time.

### Backend Tests (131 tests)

```powershell
# In the root folder with virtual env active
.venv\Scripts\python -m pytest
```

### Frontend Tests (9 tests)

```bash
cd frontend
npm run test
```
