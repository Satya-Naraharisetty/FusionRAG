# Product Requirements Document (PRD): Production-Grade Hybrid RAG Chatbot

## 1. Executive Summary

This document specifies the product requirements for a production-grade **Hybrid RAG (Retrieval-Augmented Generation) Chatbot**. The goal of this application is to serve as a showcase of modern, production-quality AI engineering. It is designed for local deployment, portfolio demonstration, and open-source release. 

Unlike generic orchestration frameworks or multi-tenant SaaS platforms, this application is laser-focused on a single objective: **providing highly accurate, grounded, and observable answers to user questions based on uploaded documents.** 

Every feature in the system is evaluated against one fundamental question: *"Does this directly improve document-grounded question answering?"* If not, it is out of scope.

---

## 2. Vision

To build a definitive reference implementation of a Hybrid RAG Chatbot that demonstrates how to transition RAG from a fragile prototype to a robust, observable, and highly reliable production system. It should serve as a premier asset for developers and AI engineers to demonstrate state-of-the-art retrieval and generation techniques to technical recruiters and hiring managers.

---

## 3. Objectives

*   **Demonstrate Technical Excellence:** Implement industry-standard best practices in retrieval (hybrid sparse/dense search, query rewriting, reranking, and compression) and generation.
*   **Rapid Recruiter Onboarding:** Enable a technical recruiter or hiring manager to spin up the application locally or view a deployed version and understand the system architecture, ingestion pipelines, and retrieval paths within 1 hour.
*   **High Groundedness & Accuracy:** Minimize hallucination by enforcing strictly grounded answer generation, backed by explicit inline citations and source highlights.
*   **Total Observability:** Demystify the "black box" of RAG by offering a complete, visual trace of the retrieval process (query rewriting, keyword/dense matching, reranking scores, and final prompt construction) within the UI.

---

## 4. Product Scope

The product scope includes:
1.  **Document Ingestion Engine:** Parsing multiple document formats, running semantic chunking, and indexing chunks in both sparse (BM25) and dense (Vector) stores.
2.  **Advanced Hybrid Retrieval Pipeline:** Query transformation, parallel sparse/dense search, metadata filtering, Reciprocal Rank Fusion (RRF), Cross-Encoder reranking, and context compression.
3.  **Conversational Chat Interface:** A responsive web UI supporting markdown streaming responses, citation visualization, source document previews, and detailed retrieval trace inspection.
4.  **Admin & Observability Dashboard:** An administration panel to manage uploaded documents, explore the vector space/chunks, view system evaluation metrics (e.g., groundedness, retrieval precision), and analyze token usage/caching efficiency.

---

## 5. Out of Scope

To prevent scope creep and maintain the application's status as a focused reference implementation, the following features are **explicitly rejected**:
*   **Multi-Tenant SaaS Architecture:** No billing integrations, team workspaces, multi-tenant database isolation, or complex subscription management.
*   **Generic Workflow Engine:** No drag-and-drop workflow builders, logic branching, or general-purpose automation node configurations.
*   **AI Agent Framework / Multi-Agent Systems:** No autonomous agent loops, tool-use execution sandboxes, or multi-agent orchestration layers.
*   **Model Registry & Feature Store:** No hosting of model weights, custom training pipelines, offline feature computation tables, or artifact stores.
*   **Identity Federation & Enterprise Security Gateways:** No SAML/Active Directory integration, complex RBAC roles (other than standard User/Admin), or advanced enterprise firewalls.
*   **Generic AI Platform:** No features that support building arbitrary, non-RAG AI applications.

---

## 6. Target Users

1.  **Technical Recruiters & Hiring Managers:** Want to quickly assess an engineer's capability in RAG, vector databases, search relevance tuning, and UI polish.
2.  **Developers & AI Engineers:** Want a robust, clean, and extensible codebase to study, customize, and show off as part of their personal portfolio.
3.  **Local Users / Self-Hosters:** Want a private, highly capable local chatbot to interact with their own documents (PDFs, notes, manuals) without leakage to external platforms.

---

## 7. User Stories

### Document Management & Organization
*   *As a user,* I want to register and log in securely so that my uploaded documents and chat histories remain private and persistent.
*   As a user, I want to upload files in PDF, DOCX, TXT, MD, HTML, CSV, and image formats (PNG, JPG, JPEG, WEBP) so that I can query diverse data sources.
*   *As a user,* I want to group documents into collections (e.g., "Tax Info", "System Architecture Specs") so that I can scope my queries to specific sets of documents.
*   *As a user,* I want to browse my uploaded documents, see their ingestion status (parsing, chunked, indexed), and delete them when they are no longer needed.

### Conversational Experience
*   *As a user,* I want to ask questions in natural language and receive grounded answers so that I don't have to manually read through hundreds of pages.
*   *As a user,* I want to see responses streamed in real-time so that I don't experience long waiting periods before reading the answer.
*   *As a user,* I want the chatbot to maintain conversation memory so that I can ask follow-up questions in context.
*   *As a user,* I want inline citations and clickable source documents so that I can instantly verify the accuracy of the generated answer.

### System Inspection & Evaluation (Technical Focus)
*   *As an AI engineer/Recruiter,* I want to view a visual step-by-step trace of how my query was rewritten, what chunks were retrieved, their individual sparse/dense scores, and how they were reranked so that I can audit retrieval performance.
*   *As an administrator,* I want to view auto-evaluation metrics (e.g., retrieval precision, answer groundedness) for my chat logs so that I can track performance degradation over time.
*   *As a developer,* I want to experiment with different prompt templates and system instructions in a search playground to see how they impact generation.

---

## 8. Functional Requirements

### 8.1. Authentication
*   **User Registration & Login:** Simple email/password sign-up and sign-in flow.
*   **Token-Based Session Management:** Secure JWT or session cookie architecture to secure API endpoints.
*   **Access Control:** Simple role separation between `User` (chat, document upload, collection management) and `Admin` (dashboard, global analytics, prompt playground, system configuration).

### 8.2. Document Management
*   **Collection Isolation:** Users can create collections. When querying, the user can select "All Documents" or filter queries to specific collections.
*   **File Status Tracking:** Ingestion states must track: `Queued`, `Processing`, `Completed`, and `Failed` (with error message logs).
*   **File Metadata Display:** Show file size, upload date, estimated token count, and number of extracted chunks in the UI.

### 8.3. Document Processing
*   **File Parsers:**
    *   **PDF:** Extraction of text, tables, and preservation of reading order.
    *   **DOCX:** Extraction of paragraphs, lists, and tabular data.
    *   **TXT & Markdown:** Plain text reading with preservation of headers/structure.
    *   **HTML:** Sanitization of tags, discarding scripts/styles, retaining semantic elements like headers, lists, and tables.
    *   **CSV:** Parsing structured rows and converting them to semantic key-value text lines or mini-tables.
    *   **Images (PNG, JPG, JPEG, WEBP):** Text extraction via OCR or a Vision-based LLM (e.g., Gemini or OpenAI) to generate structured descriptions, captions, and text transcripts of the visual content.
*   **Text Cleaning Pipeline:** Automatic removal of duplicate whitespace, boilerplate footers/headers (e.g., page numbers), and repair of word break hyphenations.

### 8.4. Metadata Extraction
*   **Automatic Attribute Extraction:** Upon document upload, the system must extract:
    *   Title, Author, Creation Date, and Document Summary.
    *   Dynamic tags or categories based on content analysis (using heuristics or a lightweight local/API model).
*   **Chunk-Level Metadata:** Each chunk must inherit parent document metadata plus chunk-specific properties (e.g., page number, section header, token count).

### 8.5. Chunking Strategies
*   **Recursive Character Chunking:** Splitting by double newlines, single newlines, spaces, and characters while maintaining target size and overlap.
*   **Semantic Chunking:** Splitting documents dynamically based on shifts in embedding similarity between adjacent sentences, preventing structural breakage of ideas.
*   **Configuration Parameters:** Admins can adjust chunk size (e.g., 512 tokens) and chunk overlap (e.g., 64 tokens) globally or per collection.

### 8.6. Embedding Generation
*   **Gemini-Only Embeddings:** Support for Google Gemini embeddings (specifically `text-embedding-004`) as the unified embedding model across all environments (local development, testing, and production).
*   **Dimension Alignment:** Vector database configurations are aligned with the Gemini embedding model's dimension (768). Local/local-ML embedding dependencies (such as torch and sentence-transformers) have been removed.

### 8.7. Hybrid Retrieval
To maximize search accuracy, the system must execute queries against two parallel indexes and combine them:
1.  **Sparse Retrieval (BM25):** 
    *   Keyword search index using full-text tokenization and stemming.
    *   Optimized for exact matches, acronyms, product codes, and specific names.
    *   Uses the standard Okapi BM25 ranking formula:
        $$Score(D, Q) = \sum_{i=1}^{n} IDF(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{avgdl}\right)}$$
        where:
        *   $k_1$ is the term frequency scaling parameter (default $= 1.5$). It controls the non-linear term frequency saturation. Higher values delay saturation, while lower values cause frequency rewards to saturate faster.
        *   $b$ is the document length normalization parameter (default $= 0.75$). It determines the scale of length normalization. A value of $1.0$ applies full length normalization (penalizing long documents), and $0.0$ applies none.

2.  **Dense Retrieval:**
    *   Vector database index (e.g., Qdrant, Chroma, or pgvector) utilizing HNSW indexes for approximate nearest neighbor (ANN) search.
    *   Optimized for semantic matching and conceptual alignment.
3.  **Metadata Filtering:**
    *   Hard metadata pre-filtering applied prior to vector search to restrict candidate pools (e.g., filter by collection ID, upload date, or file type).
4.  **Reciprocal Rank Fusion (RRF):**
    *   Merge sparse and dense search results using the RRF formula:
      $$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
      where $M$ is the set of retrievers (sparse and dense), $r_m(d)$ is the rank of document $d$ in retriever $m$, and $k$ is a constant (default $= 60$).
    *   Adjustable RRF weight balancing parameter ($\alpha$) to tune the influence of dense vs. sparse results.

### 8.8. Query Rewriting & Expansion
To handle ambiguous or conversational queries, the system must preprocess incoming user prompts:
*   **Query Rewriting:** An LLM-driven step that reformulates conversational follow-up questions into standalone search queries based on chat history.
*   **Query Expansion:** Automatically generates 3-5 synonyms or related technical terms to append to the search criteria, improving sparse retrieval recall.
*   **Multi-Query Retrieval:** Generates 3-4 different variations of the user's question from different perspectives, executes them in parallel, retrieves the union of results, and applies deduplication.

### 8.9. Cross-Encoder Reranking
*   **Reranking Pipeline:** Support for an optional reranking step (using a pass-through `IdentityReranker` by default). Heavyweight local cross-encoder models are not run by default to maintain a light memory footprint.
*   **Reranked Top-K Selection:** Select the top-$K$ (e.g., $K=5$) high-relevance chunks to pass to context compression.

### 8.10. Context Compression
*   **Token Optimization:** Compress the final chunk contexts before passing them to the generator. Use systems like `LLMLingua` or semantic sentence-level filtering to prune redundant, non-informative filler text from chunks.
*   **Information Density:** Ensure that only the most information-dense sentences of a chunk are injected into the final LLM prompt.

### 8.11. Conversation Memory
*   **Stateful Chats:** Conversations must maintain history.
*   **Memory Windows:** Support configuration of memory strategies:
    *   *Sliding Window:* Keep only the last $N$ turns of dialogue.
    *   *Summarized Memory:* Automatically generate and update a running summary of the chat history to conserve context tokens.
    *   *Vector Memory:* Embed past user conversations and retrieve relevant past questions/answers to insert as context for the current turn.

### 8.12. Streaming Responses
*   **Real-time Output:** Use Server-Sent Events (SSE) or WebSockets to stream the generation token-by-token.
*   **Parser & Renderer:** The frontend must render Markdown, code syntax highlighting, and table structures progressively as they stream, without layout flickering.

### 8.13. Source Citations
*   **Direct Grounding:** The system must map every factual statement in the generated answer to the retrieved text chunk that supported it.
*   **Inline Markers:** Render inline citation tags (e.g., `[1]`, `[2]`) in the chatbot response.
*   **Interactive Citation Drawer:** Clicking a citation marker opens a side panel highlighting the exact sentence and page in the source document.

### 8.14. Prompt Templates
*   **System Prompts:** An admin interface to customize the system prompt instruction set.
*   **Context Injection Layout:** The template must structure the input clearly, separating system instructions, context chunks (with metadata headers), chat history, and the user's new question.
*   **Fallback Strategies:** Handle cases where retrieval returns zero chunks (e.g., direct fallback to *"I cannot find any relevant information in your uploaded documents to answer this question."*).

### 8.15. Evaluation Engine
*   **Continuous Evaluation Metrics:**
    *   **Retrieval Precision/Recall:** Ratio of relevant chunks retrieved vs. total chunks.
    *   **Context Relevance:** How relevant the retrieved chunks are to the user query.
    *   **Groundedness (Faithfulness):** Check if the generated answer contains information *only* present in the context chunks (using an LLM-as-a-judge prompt or traditional NLI models).
    *   **Answer Relevance:** How directly the generated answer addresses the user's question.
*   **User Feedback Collection:** Simple UI elements (thumbs up/down) on every response, with write-in text inputs to capture user correction logs.

### 8.16. Analytics
*   **Usage Tracking Dashboard:**
    *   Total tokens consumed (prompt vs. completion).
    *   Query volume over time (hourly, daily).
    *   Cost estimates mapped to LLM provider prices.
    *   Document statistics (active collections, total disk footprint, total chunk counts).

### 8.17. Observability
*   **Visual Retrieval Trace:** The user interface must contain an collapsible "Inspect Retrieval" tab for each turn in the chat. The tab displays:
    1.  *Original Query* vs. *Rewritten Query*.
    2.  *Retrieved Chunks:* Carousel list of candidate chunks with BM25 score, Dense similarity score, RRF combined score, and final Cross-Encoder rerank score.
    3.  *Prompt Preview:* The exact compiled text string sent to the LLM (with hidden system prompts, variables, and injected context).
*   **Structured Pipeline Logging:** Backend logs must capture execution latency per sub-system (parsing, embedding, retrieval, reranking, generation) for every single call.

### 8.18. Caching
*   **Semantic Cache:** An optional cache layer (e.g., Redis or GPTSimpleVectorCache) that stores semantic representations of previously asked queries and answers. If a new query is semantically identical ($>0.95$ similarity) to a cached query, return the cached response immediately.
*   **Exact Match Cache:** Fast cache for exact string matches of queries.
*   **Retrieval Cache:** Cache vector store search results for identical queries during concurrent operations.

### 8.19. Admin Dashboard
A single control panel for system configuration and inspection:
*   **Document Manager:** Table listing all system files, collections, parse statistics, and deletion controls.
*   **System Configurator:** Form to switch embedding models, LLM providers (e.g., OpenAI, Anthropic, local Ollama), chunking parameters, and RRF coefficients.
*   **Search Playground:** A testing area where users can type a query, select specific retrievers (sparse only, dense only, hybrid, reranked), and view raw search results side-by-side with similarity metrics.
*   **Feedback & Audit Log:** List of user thumbs-up/down reports, paired with the full retrieval trace and conversation ID, allowing engineers to identify weak points in the RAG pipeline.

---

## 9. Non-Functional Requirements

### 9.1. Performance
*   **Search Latency:** The retrieval pipeline (query rewrite + hybrid search + rerank) must execute in $< 250\text{ ms}$ on standard index sizes (up to 10,000 chunks).
*   **Time-to-First-Token (TTFT):** Streaming generation must begin outputting tokens within $< 600\text{ ms}$ of receiving the request.
*   **Document Processing Throughput:** A standard 50-page PDF document must parse, chunk, embed, and index in $< 15\text{ seconds}$ on standard hardware.

### 9.2. Scalability (Single Application Focus)
*   **Horizontal scaling is not required.** The system must run optimally as a single self-contained application instance.
*   **Resource Footprint:** Memory utilization of the local server remains minimal (typically $< 2\text{ GB}$) because local embedding and reranking models are offloaded to lightweight API calls or pass-through structures.
*   **Vector Search Efficiency:** Utilize HNSW indexing to ensure vector search time scales logarithmically ($O(\log N)$) with the number of chunks.

### 9.3. Security
*   **Local Data Privacy:** All local deployments must process document chunks and vector queries locally if configured to use offline models, ensuring no document text is leaked to external APIs.
*   **Input Sanitization:** Sanitize chat prompts and document text inputs to mitigate prompt injection attacks.
*   **Secure Storage:** User passwords must be hashed using a strong hashing algorithm (e.g., bcrypt or Argon2). API keys stored on the server must be encrypted at rest.

### 9.4. Reliability & Availability
*   **Graceful Degradation:** If the reranker or query rewrite API fails, the system must gracefully fall back to raw hybrid retrieval and output the response, logging the failure warning without crashing the user session.
*   **Database Resilience:** Vector store and relational database connections must implement retry-on-disconnect logic with exponential backoff.
*   **Upload Safety:** Partially failed bulk uploads must roll back cleanly, removing orphan database entries and vector indexes for failed documents.

### 9.5. Maintainability
*   **Modular Architecture:** Strict code separation between ingestion (parsers, cleaners, chunkers), storage (databases, indexers), retrieval (search, reranking, merging), and generation (prompts, LLM clients, streaming).
*   **Clean Documentation:** The codebase must contain clear setup guides, API schemas, and schema migration definitions.
*   **Linting & Formatting:** Strict enforcement of standardized code styles (e.g., Black/PEP8 for Python, Prettier/ESLint for JavaScript).

### 9.6. Observability & Logging
*   **Structured Logs:** Standardize logging outputs in JSON format.
*   **Tracing:** Implement lightweight span tracking for key API routes to pinpoint bottleneck steps in the retrieval cycle.

### 9.7. Testing
*   **Unit Tests:** Coverage must exceed 80% for critical utility functions (chunkers, parsers, RRF merger, text cleansers).
*   **Integration Tests:** End-to-end integration tests must mock LLM responses and evaluate the correctness of the search retrieval scores.

### 9.8. Accessibility
*   **Web Standards:** The frontend must adhere to WCAG 2.1 Level AA guidelines, supporting keyboard navigation for the chat console, readable color contrast ratios, and aria-labels for dynamic icons.

### 9.9. Developer Experience (DX)
*   **Local Setup:** A single command (e.g., `docker-compose up` or a unified setup script) must build and run the entire environment.
*   **Seed Scripts:** Provide sample datasets (e.g., standard academic papers, open-source user manuals) and seeding scripts to populate the database instantly for demo runs.
*   **Environment Configuration:** All environment variables must be defined in a single, documented `.env.example` file.

---

## 10. Constraints

*   **Technology Constraints:** No enterprise orchestration engines. The app must run on a single machine or VM.
*   **Data Processing Limits:** Max file upload size must be restricted to 25MB per file to prevent out-of-memory errors on typical server sizes.
*   **Index Size Constraint:** Optimized for index sizes up to 100,000 total document chunks. Beyond this, search performance may require cluster configurations which are out of scope.

---

## 11. Risks

*   **LLM Cost Volatility:** High token generation costs when using multi-query expansion and long context reranking.
    *   *Mitigation:* Strict usage monitoring, token estimation warnings on bulk uploads, and caching layers.
*   **Retrieval Pollution:** Poorly formatted source PDFs (e.g. multi-column layouts, OCR failures) leading to corrupted text chunks.
    *   *Mitigation:* PDF parsing fallback options, layout-aware parsers, and explicit parsing previews in the Admin Dashboard.
*   **Hallucination in LLM Outputs:** Generation of answers not supported by document context.
    *   *Mitigation:* Strictly enforced system prompt boundaries, NLI-based groundedness checkers, and immediate citation requirements.

---

## 12. Success Metrics

| Metric | Target Value | Measurement Method |
| :--- | :--- | :--- |
| **Developer Onboarding Time** | $< 15\text{ minutes}$ | Time from cloning the repository to first successful local query run. |
| **Search Retrieval Latency** | $< 250\text{ ms}$ | Time spent in query expansion, vector search, sparse search, RRF, and reranking. |
| **Answer Generation TTFT** | $< 600\text{ ms}$ | Latency from prompt submission to first streamed text token on client. |
| **Groundedness Score** | $> 95\%$ | LLM-as-a-judge testing against standard evaluation QA dataset. |
| **Citation Coverage** | $100\%$ | Percentage of claims matching retrieved contexts containing active link references. |
| **Retrieval Precision @ 5** | $> 80\%$ | Ratio of relevant chunks in top 5 retrieved items over a benchmark evaluation set. |
| **Upload Processing Latency** | $< 15\text{ seconds}$ | Time to parse, chunk, embed, and index a standard 50-page PDF document. |
| **Demo Understanding Time** | $< 30\text{ minutes}$ | Time required for an external technical recruiter to read the architecture and run a query. |

---

## 13. Acceptance Criteria

*   **Correctness:** A user can upload a PDF document, ask a specific question, and receive an answer containing inline citations mapping to highlighted text within the uploaded PDF.
*   **Observability:** The chat interface must present a panel detailing the rewritten search query, list retrieved chunks with sparse/dense scores, and display the final formatted system prompt.
*   **Configuration:** The application must support swapping the underlying model (OpenAI vs. local Ollama) and retrieval configurations (RRF weights, rerank limits) entirely through environment variables or the Admin UI.
*   **Production Readiness:** The repository must contain comprehensive unit testing, documentation, a seed script, and a working Dockerfile config.

---

## 14. Product Principles

1.  **Grounded Over Clever:** It is far better for the chatbot to state *"I cannot answer this based on the retrieved documents"* than to generate a highly polished but ungrounded answer.
2.  **Transparency is Paramount:** The system must never hide its operations. Retrieval traces, raw prompt inputs, and scoring metrics are first-class citizen data.
3.  **Modular Over Coupled:** Every RAG pipeline component (sparse search, dense search, reranker, compressor) must exist as a clean, decoupled class or module that can be swapped out or upgraded independently.
4.  **Cloud-Powered, Locally Run:** The application runs locally for databases and caching (PostgreSQL, Qdrant, Redis), while offloading computationally intensive embedding and LLM generation to Google Gemini endpoints.

---

## 15. Future Enhancements

Only enhancements directly improving retrieval accuracy and grounding capability are considered for future releases:
*   **ColBERT Integration:** Implement late-interaction search models (e.g., ColBERTv2) to provide deep, token-level matching capability alongside standard dense/sparse embeddings.
*   **Parent-Child Retrieval:** Index small child chunks (e.g., 128 tokens) for highly granular search matching, but retrieve and feed the larger parent chunk context (e.g., 1024 tokens) to the generator to preserve narrative context.
*   **Corrective RAG (CRAG):** Implement a self-corrective step where an evaluator assesses retrieved document relevance. If search is deemed low quality, it automatically triggers a web-search fallback or query-refinement step prior to generator invocation.
*   **Entity Graph-Augmented RAG:** Extract document entities and relationships during ingestion, building a lightweight local knowledge graph to allow structured, multi-hop question answering.

---

## 16. Decision-Making & Development Guidelines

Before making any engineering, architectural, or implementation decision:
1.  **Review the Specs:** Read `prd.md` completely.
2.  **Review the Roadmap:** Read `phases.md` completely.
3.  **Source of Truth:** Treat `prd.md` and `phases.md` as the project's absolute sources of truth.
4.  **No Violations:** Never violate the guidelines set in the PRD.
5.  **Strict Milestone Order:** Never skip or alter the milestone execution order defined in the roadmap.
6.  **Conflict Resolution:** If a request conflicts with the PRD, explain the conflict clearly instead of implementing it.
7.  **Scope Control:** If a proposed feature does not directly improve the Hybrid RAG chatbot, reject it and explain why.
8.  **Engineering Simplicity:** Prefer simple, production-grade engineering over unnecessary abstractions.
9.  **No Unrequested Subsystems:** Do not invent new subsystems unless they are explicitly required by the PRD.
10. **Resolution of Uncertainty:** If uncertain, follow the PRD rather than making arbitrary assumptions.

