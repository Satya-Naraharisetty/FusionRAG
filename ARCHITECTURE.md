# System Architecture Manual - Hybrid RAG Chatbot

This document provides a comprehensive overview of the design, pipelines, and workflows implemented in the **Hybrid RAG Chatbot**.

---

## 1. High-Level System Architecture

The following diagram illustrates the relational layout of the backing systems, client interfaces, and operational components.

```mermaid
graph TD
    Browser["React SPA (Client UI)"]
    Nginx["Nginx Reverse Proxy"]
    FastAPI["FastAPI Web Server"]
    Postgres["PostgreSQL Database"]
    Redis["Redis Cache & Limiter"]
    Qdrant["Qdrant Vector Database"]
    S3["S3 Object Storage / MinIO"]

    Browser -->|HTTPS / WSS| Nginx
    Nginx -->|Static Assets| Browser
    Nginx -->|Proxy REST/SSE /api| FastAPI
    FastAPI -->|Credentials & Metadata| Postgres
    FastAPI -->|Sliding rate & Cache| Redis
    FastAPI -->|ANN Dense Search| Qdrant
    FastAPI -->|Raw Document Blobs| S3
```

---

## 2. Ingestion & Document Processing Pipeline

The ingestion pipeline handles raw uploads, text extraction, structural cleaning, chunking, vector embedding generation, and indexing.

```mermaid
flowchart TD
    Upload["Upload File via API"] --> Extractor["ExtractorFactory Selection"]
    Extractor --> Text["Extract Plaintext (PDF, DOCX, TXT, MD)"]
    Text --> Clean["TextCleaner (Whitespace, Encoding, Sanitization)"]
    Clean --> Chunk["ChunkingService (Recursive / Semantic Split)"]
    Chunk --> Batch["Batch Embedding Request"]
    Batch --> Index["Index Vectors in Qdrant & Save Metadata"]
    Batch --> DB["Save Chunks SQL Metadata in Postgres"]
```

---

## 3. Hybrid Retrieval Pipeline

The retrieval engine combines dense semantic search and sparse term-frequency keyword matching to achieve high precision and recall.

```mermaid
sequenceDiagram
    autonumber
    participant Client as User / Chat Endpoint
    participant Retrieval as RetrievalService
    participant BM25 as InMemoryBM25Index (Sparse)
    participant Qdrant as QdrantVectorStore (Dense)
    participant Fusion as RRF Fusion Engine
    participant Rerank as Cross-Encoder Reranker
    participant Diversity as MMR Selector

    Client->>Retrieval: Query (User request)
    par Sparse Retrieve
        Retrieval->>BM25: Sparse search (BM25 Token matching)
        BM25-->>Retrieval: Return Top-K sparse chunks
    and Dense Retrieve
        Retrieval->>Qdrant: Dense search (Cosine ANN Query)
        Qdrant-->>Retrieval: Return Top-K dense chunks
    end
    Retrieval->>Fusion: Fuse results (Reciprocal Rank Fusion)
    Fusion-->>Retrieval: Ranked fused list
    Retrieval->>Rerank: Refine rankings (Cross-Encoder models)
    Rerank-->>Retrieval: Reordered chunks
    Retrieval->>Diversity: Filter redundant data (MMR selector)
    Diversity-->>Retrieval: Top-N diverse context chunks
    Retrieval-->>Client: Final Context Payload
```

---

## 4. Authentication & JWT Session Flow

Access is controlled via short-lived JWT tokens and secure, rotated, HTTP-only refresh cookies.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client Browser
    participant API as FastAPI /auth
    participant DB as PostgreSQL (Sessions)

    User->>API: POST /login (Credentials)
    API->>API: Verify password (Argon2id)
    API->>DB: Create Refresh Session
    API-->>User: Set HTTP-Only Cookie (Refresh Token) & JSON body (Access Token)
    Note over User, API: Standard requests include Bearer Access Token in Header
    
    User->>API: POST /refresh-token (No Access Token / Cookies sent)
    alt Token Valid & Unused
        API->>DB: Rotate Refresh Token (Create new session, revoke old)
        API-->>User: Set New Cookie (Refresh Token) & JSON body (New Access Token)
    else Token Reused (Theft Detection)
        API->>DB: Revoke all user sessions immediately (Breach)
        API-->>User: Clear Cookies & return 401 Unauthorized
    end
```

---

## 5. Agentic Tool Calling Loop

When a request requires calculation or database lookups, the orchestrator invokes a feedback loop to evaluate tools.

```mermaid
flowchart TD
    Input["User Query"] --> LLM["LLM Router (Gemini/OpenAI)"]
    LLM --> ToolCall{Tool Call Required?}
    ToolCall -->|Yes| Executor["Tool Executor Sandbox"]
    Executor --> Result["Return ToolResult to LLM Context"]
    Result --> LLM
    ToolCall -->|No| Answer["Return final Grounded Answer"]
```

---

## 6. Evaluation Framework & Observability Console

To prevent regression, offline dataset runners evaluate retrieval and generation metrics.

*   **Faithfulness**: Asserts the generation is fully grounded in the retrieved chunks.
*   **Answer Relevancy**: Asserts the response directly answers the user's prompt.
*   **Context Recall & Precision**: Asserts the retrieval contains and isolates the exact answers.
*   **Circuit-Breaker Failover**: Automatically redirects LLM queries between Gemini and OpenAI in case of API degradation.

### Visual Admin Dashboard (`/admin/dashboard`)
We have introduced a visual frontend console allowing admin users to:
1.  **Observability Traces**: View real-time token counts, response latency (retrieval vs. generation), cost estimates, and full conversation traces.
2.  **Evaluations Suite**: View runs history, trigger offline benchmarks, perform regression comparison checking, and render styled HTML performance reports directly in-app.

The backend exposes these operations via `/api/v1/observability` and `/api/v1/evaluation` endpoints, restricted via the `check_admin_user` dependency guard.
