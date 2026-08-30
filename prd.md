# Product Requirements Document (PRD): Production-Grade Fusion RAG Chatbot

## 1. Executive Summary

This document specifies the product requirements for a production-grade **Fusion RAG (Retrieval-Augmented Generation) Chatbot**. The goal of this application is to serve as a premier reference implementation of modern, production-quality AI engineering. It is designed for containerized local deployment, portfolio demonstration, and reliable production operations.

The platform provides **highly accurate, grounded, observable, and multi-strategy answers** based on user-uploaded documents, featuring dual-branch hybrid retrieval (PostgreSQL FTS / BM25 + Qdrant Dense ANN), Reciprocal Rank Fusion (RRF), Cross-Encoder joint cross-attention reranking, Adaptive RAG orchestration, agentic tool execution sandboxes, and full OpenTelemetry/Prometheus observability.

---

## 2. Vision

To build a definitive reference implementation of a Fusion RAG Chatbot that demonstrates how to transition RAG from a fragile prototype to a robust, observable, resilient, and enterprise-grade production platform.

---

## 3. Objectives

* **Demonstrate Technical Excellence:** Implement industry-standard best practices in hybrid retrieval (dense vector ANN + sparse keyword search, query rewriting, reranking, context selection) and streaming generation.
* **Rapid Recruiter & Engineer Onboarding:** Enable an engineer or recruiter to clone the repository and run the full stack via `docker compose up` within minutes.
* **High Groundedness & Accuracy:** Minimize hallucination by enforcing strictly grounded answer generation, backed by explicit inline citations, source document previews, and XML prompt isolation.
* **Total Observability:** Demystify the RAG process by providing visual in-app retrieval traces, token usage breakdown, latency waterfalls, and OpenTelemetry/Prometheus integration.
* **Resilient Multi-Strategy Retrieval:** Automatically adapt between Direct Retrieval, HyDE (Hypothetical Document Embeddings), Multi-Hop Decomposition, and Specialist Multi-Agent execution based on query complexity.

---

## 4. Product Scope

The product scope includes:
1. **Multi-Format Ingestion Engine:** Parses PDF, DOCX, TXT, Markdown (`.md`), HTML, CSV, and Images (PNG, JPG, JPEG, WEBP via Gemini Vision OCR), with magic-byte validation, zip-bomb protection, and ClamAV malware scanning.
2. **Two-Tier Document Management:**
   - **Global Library Documents**: Shared across conversations, managed on the Documents page, addressable via `@documents` mentions.
   - **Conversation-Scoped Attachments**: Uploaded directly in chat, auto-used for context, and cascade-deleted when the conversation is removed.
3. **Advanced Hybrid Retrieval Engine:** Parallel sparse (PostgreSQL FTS / InMemoryBM25) and dense (Qdrant HNSW) search, Reciprocal Rank Fusion ($k=60$), Maximal Marginal Relevance ($\lambda=0.5$), and Cross-Encoder joint reranking (Jina AI REST API).
4. **Adaptive RAG & Multi-Agent Orchestration:** Dynamic query routing, HyDE execution, query expansion & decomposition, evidence sufficiency evaluation, and autonomous replanning.
5. **Agentic Tool Sandbox:** AST-sandboxed math evaluation (`SafeCalculator`), web search integration (SerpAPI / Firecrawl), with execution timeouts and recursion guards.
6. **Authentication & Session Security:** NIST SP 800-63B compliant Argon2id password hashing, stateless JWT HS256 access tokens, rotated HTTP-only refresh cookies, OAuth 2.0 (Google/GitHub), and Resend transactional email verification.
7. **Conversational Chat Interface:** React SPA with SSE streaming responses, markdown syntax highlighting (Shiki), interactive citation inspection, message drafts, search, and JSON/Markdown export.
8. **Admin & Observability Suite:** In-app visual dashboard (`/admin/dashboard`) showing live KPIs, execution trace waterfalls, and RAG evaluation benchmarks (Ragas / DeepEval) with regression tracking.

---

## 5. Out of Scope

The following features remain explicitly outside project scope:
* **Complex Multi-Tenant Billing / SaaS Metering:** No Stripe/credit card billing or subscription gating.
* **Generic Drag-and-Drop Workflow Builders:** No visual node-based workflow graph editors.
* **Hosting Local Deep Learning Weights:** No PyTorch, CUDA, or heavy local model files (all neural inference is offloaded to fast cloud APIs).
* **Enterprise SAML / Active Directory Gateways:** Standard email/password and Google/GitHub OAuth are provided; legacy enterprise SAML is excluded.

---

## 6. Target Users

1. **Technical Recruiters & Hiring Managers:** Assess an engineer's depth in RAG architectures, vector databases, search relevance, distributed systems, and UX polish.
2. **Developers & AI Engineers:** Study, fork, and customize a production-ready, clean Python/React codebase for personal projects and portfolio showcases.
3. **Local Self-Hosters & Power Users:** Interact privately and reliably with personal/team documents (PDFs, research papers, manuals, financial reports).

---

## 7. Functional Requirements

### 7.1. Authentication & User Management
* **Registration & Login:** Email/password authentication using Argon2id password hashing.
* **Email Verification & Magic Links:** Transactional emails powered by Resend with expiring verification tokens.
* **OAuth 2.0:** One-click social sign-in with Google and GitHub.
* **Token Rotation & Replay Revocation:** 15-minute JWT access tokens and single-use 7-day HTTP-only refresh cookies. Immediate revocation of all user sessions upon detected refresh token replay.
* **Account Deletion:** Password-gated `DELETE /api/v1/auth/account` endpoint with strict rate limiting and cascade cleanup.
* **Single Admin Invariant:** Declarative promotion of `ADMIN_EMAIL` and automatic demotion of all other accounts to ensure exactly one administrator.

### 7.2. Two-Tier Document Ingestion
* **Supported Formats:** PDF, DOCX, TXT, Markdown (`.md`), HTML, CSV, and Images (PNG, JPG, JPEG, WEBP).
* **File Validation:** Magic-byte signature checking and zip-bomb decompression ratio limits (< 100x).
* **Malware Defense:** Streamed socket virus scanning via ClamAV daemon (`clamd` TCP port 3310), failing closed in production.
* **Deduplication:** SHA-256 content checksumming preventing redundant uploads.
* **Storage Abstraction:** PostgreSQL binary BLOB storage (`document_files` table) or local filesystem (`UPLOAD_DIR`).
* **Asynchronous Queue:** Durable Redis Streams task queue (`stream:jobs:document_processing`) with consumer groups, ACK acknowledgments, dead-letter routing, and automatic backoff retries.

### 7.3. Text Processing & Chunking
* **Text Cleaner:** Whitespace normalization, unicode sanitization, line break repair, and header/footer stripping.
* **Metadata Extraction:** Automated extraction of title, author, creation date, summary, tags, language, and word count.
* **Hierarchical Chunking:** Support for Recursive Character, Semantic (similarity shift), Parent-Child, Sentence-Window, and Contextual chunking strategies.

### 7.4. Dense & Sparse Hybrid Retrieval
* **Dual-Branch Search:**
  * **Dense Vector Search:** Qdrant HNSW vector index with 768-dimensional embeddings generated via `jina-embeddings-v3` or `text-embedding-004`. All vector searches are strictly isolated by `user_id` payload filters.
  * **Sparse Lexical Search:** PostgreSQL Full-Text Search using `to_tsvector`, `ts_rank_cd`, and `websearch_to_tsquery` on GIN indexes, or in-memory BM25 with shared tokenization caching.
* **Reciprocal Rank Fusion (RRF):** Merges dense and sparse rankings with configurable $k=60$ and optional dense/sparse weighting.
* **Maximal Marginal Relevance (MMR):** Selects diverse candidates with $\lambda=0.5$.
* **Cross-Encoder Reranking:** Jina AI REST API (`jina-reranker-v2-base-multilingual`) performing joint cross-attention relevance scoring over candidate pairs.
* **Context Selection:** Filters candidates by document scope, minimum score, and enforces a token budget (default 6,000 tokens).

### 7.5. Adaptive RAG & Agentic Orchestration
* **Query Classification:** Deterministically classifies queries as Direct, HyDE, Multi-Hop, or Specialist.
* **Hypothetical Document Embeddings (HyDE):** Generates hypothetical answer passages to bridge semantic query-document gaps.
* **Multi-Hop Decomposition:** Splits complex multi-part questions into sequential sub-retrieval steps.
* **Evidence Sufficiency Evaluator:** Inspects candidate relevance and triggers autonomous replanning when retrieved evidence is insufficient.
* **Agentic Tools:**
  * `SafeCalculator`: AST-based arithmetic evaluator blocking dangerous operations and preventing exponential CPU attacks.
  * `WebSearchTool`: Live internet search fallback via SerpAPI / Firecrawl.

### 7.6. Conversational Chat & Streaming
* **Server-Sent Events (SSE):** Progressive streaming of response tokens, inline citations, and execution trace metadata.
* **Prompt Isolation:** Strict `<retrieved_context>` XML encapsulation with system instructions establishing retrieved text as untrusted data to neutralize prompt injection.
* **Conversation Memory:** Sliding window context memory with rolling background summaries for long conversations.
* **Markdown & Code Rendering:** Client-side markdown formatting with Shiki syntax highlighting, copy blocks, and interactive citation popups.

### 7.7. Observability, Analytics & Evaluation
* **In-App Admin Console (`/admin/dashboard`):** Real-time analytics, token volume charts, latency percentiles, and full LLM execution trace waterfalls.
* **Automated Quality Evaluations:** Benchmark runs testing Faithfulness, Answer Relevancy, Context Precision, and Context Recall using Ragas and DeepEval against golden datasets.
* **Regression Runner:** Compares run results to historical baselines (`baseline_v1.json`, `baseline_v2.json`, `baseline_v3.json`) and renders HTML reports.
* **OpenTelemetry & Prometheus:** OpenTelemetry distributed tracing exported to Jaeger (`:4317` / `:16686`) and Prometheus metrics (`:9090`) visualized in Grafana (`:3000`).

---

## 8. Non-Functional Requirements

| Domain | Requirement | Target Metric |
|---|---|---|
| **Retrieval Latency** | Query rewrite + hybrid search + reranking | $< 250\text{ ms}$ (p95 on $\le 10,000$ chunks) |
| **Streaming TTFT** | Time-to-first-token on streaming responses | $< 600\text{ ms}$ |
| **Container Footprint** | Zero PyTorch / CUDA local weights | Image size $< 450\text{ MB}$, cold start $< 1\text{ s}$ |
| **Groundedness** | Absence of hallucinated factual statements | $> 90\%$ on golden evaluation QA datasets |
| **Security** | NIST password compliance, secure cookies, prompt injection defense | Zero hardcoded secrets, fail-fast production validation |
| **Concurrency** | Non-blocking async event loop with scaled connection pools | 50+ concurrent queries with zero deadlock |

---

## 9. Product Principles

1. **Grounded Over Clever:** The assistant prioritizes truthful citation-grounded facts over ungrounded speculation.
2. **Total Observability:** The system exposes its decision branches, retrieval scores, and prompt construction.
3. **Decoupled Architecture:** Ingestion, storage, retrieval, orchestration, and generation operate as independent, swappable components.
4. **Zero-PyTorch Cloud Inference:** Vector embeddings, cross-encoder reranking, and generation run via fast, resilient REST APIs.


