import time
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.db.models import Base
from app.documents.domain.models import Chunk, DocumentRetrievalScope
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.services.index_cache import InMemoryIndexCache
from app.documents.services.postgres_sparse_retriever import PostgresSparseRetriever
from app.documents.services.sparse_index import InMemoryBM25Index
from tests.db import TEST_DATABASE_URL


def _sync_setup_benchmark_db(sync_engine):
    Base.metadata.create_all(bind=sync_engine)
    sync_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=sync_engine
    )
    db = sync_session_local()
    try:
        db.execute(text("DELETE FROM document_embeddings;"))
        db.execute(text("DELETE FROM document_chunks;"))
        db.execute(text("DELETE FROM documents;"))
        db.execute(text("DELETE FROM conversations;"))
        db.execute(text("DELETE FROM refresh_sessions;"))
        db.execute(text("DELETE FROM users;"))
        db.execute(
            text(
                "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector "
                "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;"
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_search_vector ON document_chunks USING gin (search_vector);"
            )
        )
        db.commit()
    finally:
        db.close()
    sync_engine.dispose()


@pytest.mark.asyncio
async def test_benchmark_bm25_vs_postgres_fts():
    sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(async_url, poolclass=NullPool)
    _sync_setup_benchmark_db(sync_engine)

    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    corpus_texts = [
        "Distributed systems require consensus algorithms like Raft and Paxos for state machine replication.",
        "PostgreSQL full-text search provides powerful GIN indexing and tsvector document matching.",
        "Vector databases like Qdrant store high-dimensional dense embeddings for semantic search.",
        "Reciprocal Rank Fusion fuses ordinal rankings from multiple retrieval pipelines seamlessly.",
        "Redis Streams enable durable event streaming, consumer groups, and pending entry list recovery.",
        "Asynchronous task queues handle heavy document chunking and embedding generation in background workers.",
        "Magic bytes validation inspects the first initial header bytes of uploaded files to block polyglot attacks.",
        "Cross-encoder rerankers jointly encode query and document pairs to produce precise relevance scores.",
        "Maximum Marginal Relevance balances retrieval relevance with document diversity to prevent redundancy.",
        "Query expansion enriches natural language prompts with synonyms and related domain terminology.",
    ] * 10  # 100 total chunks

    async with session_factory() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="bench_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.flush()

        doc_id = uuid4()
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="benchmark_corpus.txt",
                original_filename="benchmark_corpus.txt",
                content_type="text/plain",
                file_size=10000,
                checksum="benchchk",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.flush()

        db_chunks = []
        domain_chunks = []
        for idx, text_content in enumerate(corpus_texts):
            cid = uuid4()
            db_chunks.append(
                SQLAlchemyChunk(
                    id=cid,
                    document_id=doc_id,
                    chunk_index=idx,
                    text=text_content,
                    character_start=idx * 100,
                    character_end=(idx + 1) * 100,
                    token_estimate=15,
                    metadata_json={"document_scope": "LIBRARY", "document_name": "benchmark_corpus.txt"},
                )
            )
            domain_chunks.append(
                Chunk(
                    id=cid,
                    document_id=doc_id,
                    chunk_index=idx,
                    text=text_content,
                    character_start=idx * 100,
                    character_end=(idx + 1) * 100,
                    token_estimate=15,
                    metadata={"document_scope": "LIBRARY", "document_name": "benchmark_corpus.txt"},
                    created_at=datetime.now(UTC),
                )
            )
        session.add_all(db_chunks)
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        index_cache = InMemoryIndexCache()
        bm25_index = InMemoryBM25Index(chunk_repo=chunk_repo, index_cache=index_cache)
        await bm25_index.index_chunks(user_id, domain_chunks)

        pg_retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        queries = [
            "PostgreSQL full-text search GIN",
            "Redis Streams durable consumer groups",
            "Vector databases Qdrant dense embeddings",
            "Consensus algorithms Raft Paxos",
            "Cross-encoder rerankers relevance scores",
        ]

        bm25_latencies = []
        pg_latencies = []
        overlaps = []

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)

        for q in queries * 5:  # 25 total benchmark runs
            # Measure InMemoryBM25
            t0 = time.perf_counter()
            bm25_results = await bm25_index.search(
                query=q, user_id=user_id, top_k=5, retrieval_scope=scope
            )
            bm25_latencies.append((time.perf_counter() - t0) * 1000)

            # Measure PostgresSparseRetriever
            t0 = time.perf_counter()
            pg_results = await pg_retriever.search(
                query=q, user_id=user_id, top_k=5, retrieval_scope=scope
            )
            pg_latencies.append((time.perf_counter() - t0) * 1000)

            # Calculate top-k overlap (Jaccard similarity on chunk IDs)
            bm25_ids = {r.chunk_id for r in bm25_results}
            pg_ids = {r.chunk_id for r in pg_results}
            if bm25_ids or pg_ids:
                jaccard = len(bm25_ids & pg_ids) / len(bm25_ids | pg_ids)
                overlaps.append(jaccard)

        bm25_p50 = float(np.percentile(bm25_latencies, 50))
        bm25_p95 = float(np.percentile(bm25_latencies, 95))
        pg_p50 = float(np.percentile(pg_latencies, 50))
        pg_p95 = float(np.percentile(pg_latencies, 95))
        avg_overlap = float(np.mean(overlaps)) if overlaps else 1.0

        print("\n--- BENCHMARK RESULTS: InMemoryBM25 vs PostgreSQL FTS ---")
        print(f"InMemoryBM25:      p50={bm25_p50:.2f}ms, p95={bm25_p95:.2f}ms")
        print(f"PostgreSQL FTS:    p50={pg_p50:.2f}ms, p95={pg_p95:.2f}ms")
        print(f"Ranking Overlap:   {avg_overlap * 100:.1f}%")

        assert len(bm25_latencies) == 25
        assert len(pg_latencies) == 25
        assert pg_p50 < 100.0  # PostgreSQL query should comfortably execute in <100ms


@pytest.mark.asyncio
async def test_benchmark_multi_worker_queue_throughput():
    """
    Measures enqueue latency, multi-worker throughput, and total processing duration
    across 10, 50, and 100 job batches using real Redis Streams.
    """
    import asyncio

    import redis.asyncio as aioredis

    from app.core.queue.interfaces import Job, JobDispatcher, JobHandler, JobResult
    from app.core.queue.redis_queue import RedisStreamTaskQueue
    from app.core.queue.worker import QueueWorker

    redis_client = aioredis.from_url("redis://localhost:6379/0", decode_responses=False)
    prefix = f"bench:{uuid4().hex[:8]}"
    stream_name = f"{prefix}:stream"
    group_name = f"{prefix}:group"

    try:
        results_summary = []

        for job_count, worker_count in [(10, 1), (10, 2), (50, 1), (50, 2), (100, 2)]:
            sub_stream = f"{stream_name}:{job_count}_{worker_count}"
            sub_group = f"{group_name}:{job_count}_{worker_count}"

            # Measure Enqueue latency
            enqueue_latencies = []
            producer_queue = RedisStreamTaskQueue(
                redis_client=redis_client,
                stream_name=sub_stream,
                consumer_group=sub_group,
            )
            await producer_queue.ensure_consumer_group()

            for i in range(job_count):
                t0 = time.perf_counter()
                await producer_queue.enqueue(
                    task_type="BENCH_TASK",
                    payload={"idx": i},
                )
                enqueue_latencies.append((time.perf_counter() - t0) * 1000)

            # Setup workers
            processed: list[int] = []

            class BenchHandler(JobHandler):
                async def handle(self, job: Job) -> JobResult:
                    processed.append(job.payload["idx"])
                    return JobResult(success=True)

            dispatcher = JobDispatcher()
            dispatcher.register("BENCH_TASK", BenchHandler())

            workers = []
            for w in range(worker_count):
                q = RedisStreamTaskQueue(
                    redis_client=redis_client,
                    stream_name=sub_stream,
                    consumer_group=sub_group,
                    consumer_name=f"bench-worker-{w}",
                )
                workers.append(QueueWorker(task_queue=q, dispatcher=dispatcher, concurrency=4, block_ms=200))

            t_start = time.perf_counter()
            for worker in workers:
                await worker.start()

            for _ in range(200):
                if len(processed) >= job_count:
                    break
                await asyncio.sleep(0.02)

            for worker in workers:
                await worker.stop(timeout_seconds=0.5)

            t_total = time.perf_counter() - t_start
            throughput = job_count / t_total if t_total > 0 else 0
            p50_enq = float(np.percentile(enqueue_latencies, 50))
            p95_enq = float(np.percentile(enqueue_latencies, 95))

            results_summary.append({
                "jobs": job_count,
                "workers": worker_count,
                "total_time_s": t_total,
                "throughput_jobs_sec": throughput,
                "enq_p50_ms": p50_enq,
                "enq_p95_ms": p95_enq,
            })
            assert len(processed) == job_count

        print("\n--- BENCHMARK RESULTS: Redis Streams Multi-Worker Throughput ---")
        for res in results_summary:
            print(
                f"Jobs: {res['jobs']:3d} | Workers: {res['workers']} | "
                f"Total Time: {res['total_time_s']:.3f}s | "
                f"Throughput: {res['throughput_jobs_sec']:.1f} jobs/s | "
                f"Enqueue p50: {res['enq_p50_ms']:.2f}ms, p95: {res['enq_p95_ms']:.2f}ms"
            )

    finally:
        keys = await redis_client.keys(f"{prefix}:*")
        if keys:
            await redis_client.delete(*keys)
        await redis_client.aclose()

