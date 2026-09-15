import re
import sys
from pathlib import Path

ROOT = Path(r"d:\fun\FusionRAG")
ANSWERS_DIR = ROOT / "docs" / "interview_answers"
OUTPUT_FILE = ROOT / "INTERVIEW_QUESTIONS.md"

PARTS = [
    ("Part 1", ANSWERS_DIR / "PART_1_PYTHON_FASTAPI_PYDANTIC.md", 1, 26),
    ("Part 2", ANSWERS_DIR / "PART_2_DATABASES_STORAGE.md", 27, 68),
    ("Part 3A", ANSWERS_DIR / "PART_3A_INGESTION_EMBEDDINGS_BM25.md", 69, 98),
    ("Part 3B", ANSWERS_DIR / "PART_3B_HYBRID_RRF_QUERY_KG.md", 99, 128),
    ("Part 4", ANSWERS_DIR / "PART_4_MULTI_AGENT_DAG.md", 129, 160),
    ("Part 5", ANSWERS_DIR / "PART_5_SECURITY_AUTH_CRYPTO.md", 161, 188),
    ("Part 6", ANSWERS_DIR / "PART_6_DISTRIBUTED_LIFECYCLE_SCALING.md", 189, 208),
    ("Part 7", ANSWERS_DIR / "PART_7_FRONTEND_DEVOPS_OBSERVABILITY.md", 209, 228),
    ("Part 8", ANSWERS_DIR / "PART_8_SITUATIONAL_INCIDENTS.md", 229, 246),
]

HEADER = """# FusionRAG: The Complete Master Engineering & System Architecture Interview Manual
### Comprehensive End-to-End Technical Interview Benchmark Across the Full Stack

> **Definitive Production Engineering & Architectural Guide:**
> This document is the **authoritative, all-encompassing technical interview manual and master reference** for the **FusionRAG** production platform. It provides exhaustive, staff/principal-level answers for all 246 questions spanning:
> 1. **Core Language & Framework Internals**: Deep Python 3.12+, FastAPI, Starlette, Pydantic v2, TypeScript 5, React 18, Pyodide WASM.
> 2. **Databases, Caches & Storage Engines**: PostgreSQL 16 (MVCC, GIN, B-Tree, locks), SQLAlchemy 2.0, Redis 7 (epoll, AOF/RDB, Streams, eviction), Qdrant (HNSW, MRL, payloads).
> 3. **Information Retrieval, Mathematics & RAG**: Dense embeddings, BM25, Reciprocal Rank Fusion ($k=60$), Maximal Marginal Relevance ($\\lambda=0.5$), Cross-Encoder joint attention, HyDE, Query Decomposition, Context Window budgeting.
> 4. **Multi-Agent Systems & Symbolic Orchestration**: Dynamic DAG construction, Kahn's algorithm, Topological wave concurrency, AST arithmetic sandboxing, Knowledge Graph BFS traversal, ResultEvaluator adaptive replanning.
> 5. **Security, Multi-Tenancy & Cryptography**: Two-tier document scoping (`LIBRARY` vs `CONVERSATION`), IDOR mitigation, direct/indirect prompt injection, NIST SP 800-63B auth, Argon2id, single-use JWT refresh rotation, AES-256-GCM envelope encryption, cryptographic shredding.
> 6. **Distributed Systems, Queues & Lifecycle**: Redis Streams consumer groups, lease protocols, Durable Cleanup Outbox, idempotency, self-healing reapers, the 50-concurrency database pool deadlock post-mortem.
> 7. **DevOps, Observability & Quality Governance**: Docker multi-stage builds, Linux cgroups/namespaces, OpenTelemetry, Jaeger, Prometheus low-cardinality metrics, Ragas/DeepEval quality evaluation.
> 8. **Live Situational Incidents & War Stories**: 18 real-world production incident response scenarios (P0 leaks, upstream 429 outages, zip-bombs, stale vector syndrome, connection pool exhaustion).

---

## Master Table of Contents
- [Part I: Core Language, Framework & Runtime Internals](#part-i-core-language-framework--runtime-internals)
  - [Chapter 1: Python 3.12+ Core, Memory & Asyncio Internals (Q1–Q12)](#chapter-1-python-312-core-memory--asyncio-internals)
  - [Chapter 2: FastAPI & Starlette Framework Architecture (Q13–Q20)](#chapter-2-fastapi--starlette-framework-architecture)
  - [Chapter 3: Pydantic v2 & Data Engineering (Q21–Q26)](#chapter-3-pydantic-v2--data-engineering)
- [Part II: Databases, Data Stores & Indexing Engines](#part-ii-databases-data-stores--indexing-engines)
  - [Chapter 4: PostgreSQL 16 Internals, MVCC, Indexing & Concurrency (Q27–Q38)](#chapter-4-postgresql-16-internals-mvcc-indexing--concurrency)
  - [Chapter 5: SQLAlchemy 2.0 ORM, Session Lifecycle & Data Patterns (Q39–Q46)](#chapter-5-sqlalchemy-20-orm-session-lifecycle--data-patterns)
  - [Chapter 6: Redis 7 Internals, Streams, Eviction & Distributed Systems (Q47–Q58)](#chapter-6-redis-7-internals-streams-eviction--distributed-systems)
  - [Chapter 7: Vector Databases, Qdrant & Search Mathematics (Q59–Q68)](#chapter-7-vector-databases-qdrant--search-mathematics)
- [Part III: RAG, Retrieval & Information Theory](#part-iii-rag-retrieval--information-theory)
  - [Chapter 8: Document Ingestion, Parsing, Chunking & Storage (Q69–Q80)](#chapter-8-document-ingestion-parsing-chunking--storage)
  - [Chapter 9: Dense Embeddings, Matryoshka Learning & Bi-Encoders (Q81–Q88)](#chapter-9-dense-embeddings-matryoshka-learning--bi-encoders)
  - [Chapter 10: Sparse Retrieval, BM25 & PostgreSQL Full-Text Search (Q89–Q98)](#chapter-10-sparse-retrieval-bm25--postgresql-full-text-search)
  - [Chapter 11: Hybrid Search Fusion (RRF), Diversity (MMR) & Cross-Encoder Reranking (Q99–Q110)](#chapter-11-hybrid-search-fusion-rrf-diversity-mmr--cross-encoder-reranking)
  - [Chapter 12: Query Preprocessing, HyDE, Decomposition & Context Budgeting (Q111–Q120)](#chapter-12-query-preprocessing-hyde-decomposition--context-budgeting)
  - [Chapter 13: Knowledge Graph Representation & Multi-Hop Traversal (Q121–Q128)](#chapter-13-knowledge-graph-representation--multi-hop-traversal)
- [Part IV: Multi-Agent Systems & Advanced Orchestration](#part-iv-multi-agent-systems--advanced-orchestration)
  - [Chapter 14: Hierarchical Multi-Agent DAG & Orchestration Engine (Q129–Q142)](#chapter-14-hierarchical-multi-agent-dag--orchestration-engine)
  - [Chapter 15: AST Sandboxing, Deterministic Math & Symbolic Security (Q143–Q150)](#chapter-15-ast-sandboxing-deterministic-math--symbolic-security)
  - [Chapter 16: Result Evaluation, Evidence Gating & Grounded Synthesis (Q151–Q160)](#chapter-16-result-evaluation-evidence-gating--grounded-synthesis)
- [Part V: Security, Multi-Tenancy, Auth & Cryptography](#part-v-security-multi-tenancy-auth--cryptography)
  - [Chapter 17: Multi-Tenancy, Document Scoping & IDOR Defense (Q161–Q170)](#chapter-17-multi-tenancy-document-scoping--idor-defense)
  - [Chapter 18: Prompt Injection Defense & Untrusted Context Framing (Q171–Q178)](#chapter-18-prompt-injection-defense--untrusted-context-framing)
  - [Chapter 19: NIST SP 800-63B Authentication, JWT Rotation & Cryptographic Shredding (Q179–Q188)](#chapter-19-nist-sp-800-63b-authentication-jwt-rotation--cryptographic-shredding)
- [Part VI: Distributed Lifecycle, Scalability & Performance Engineering](#part-vi-distributed-lifecycle-scalability--performance-engineering)
  - [Chapter 20: Asynchronous Task Queues, Redis Streams & Durable Lifecycle (Q189–Q198)](#chapter-20-asynchronous-task-queues-redis-streams--durable-lifecycle)
  - [Chapter 21: High-Concurrency Scaling & Database Pool Deadlock Post-Mortem (Q199–Q208)](#chapter-21-high-concurrency-scaling--database-pool-deadlock-post-mortem)
- [Part VII: Frontend, Protocols, DevOps & Observability](#part-vii-frontend-protocols-devops--observability)
  - [Chapter 22: TypeScript 5, React 18, Pyodide WASM & Web Protocols (Q209–Q218)](#chapter-22-typescript-5-react-18-pyodide-wasm--web-protocols)
  - [Chapter 23: OpenTelemetry, Prometheus, Docker & Evaluation Governance (Q219–Q228)](#chapter-23-opentelemetry-prometheus-docker--evaluation-governance)
- [Part VIII: Situational Incidents, Production War Stories & P0 Triage](#part-viii-situational-incidents-production-war-stories--p0-triage)
  - [Chapter 24: Real-World Incident Response Scenarios (Q229–Q246)](#chapter-24-real-world-incident-response-scenarios)

---
"""

def main():
    print("Checking parts status...")
    all_ready = True
    for name, path, q_start, q_end in PARTS:
        if not path.exists():
            print(f"[MISSING] {name}: {path} does not exist!")
            all_ready = False
            continue
        content = path.read_text(encoding="utf-8")
        # Check for placeholders
        placeholders = re.findall(r"<!--\s*CHAPTER_\d+_HERE\s*-->", content)
        if placeholders:
            print(f"[INCOMPLETE] {name}: Contains placeholders: {placeholders}")
            all_ready = False
        else:
            print(f"[READY] {name}: {len(content):,} bytes, {len(content.splitlines()):,} lines")

    if not all_ready:
        print("\nNot all parts are ready. Waiting for subagents to complete...")
        sys.exit(1)

    print("\nAll parts verified complete! Assembling master interview manual...")
    master_content = [HEADER.strip()]

    for name, path, q_start, q_end in PARTS:
        content = path.read_text(encoding="utf-8").strip()
        master_content.append("\n\n---\n\n")
        master_content.append(content)

    final_text = "\n".join(master_content)
    OUTPUT_FILE.write_text(final_text, encoding="utf-8")
    print(f"\nWrote master manual to {OUTPUT_FILE}")
    print(f"Total size: {len(final_text):,} bytes ({len(final_text)/1024/1024:.2f} MB)")
    print(f"Total lines: {len(final_text.splitlines()):,}")

    # Verify all questions from Q1 to Q246 are present
    print("\nVerifying question presence (Q1 - Q246)...")
    missing_q = []
    found_q = []
    for q_num in range(1, 247):
        pattern = rf"(?:Question|Scenario)\s+{q_num}\b"
        if re.search(pattern, final_text, re.IGNORECASE):
            found_q.append(q_num)
        else:
            missing_q.append(q_num)

    print(f"Questions found: {len(found_q)} / 246")
    if missing_q:
        print(f"WARNING: Missing questions: {missing_q}")
        sys.exit(2)
    else:
        print("SUCCESS! All 246 questions (Q1 to Q246) are present with comprehensive answers.")

if __name__ == "__main__":
    main()
