from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.core.queue.handlers import GenerateEmbeddingsJobHandler
from app.core.queue.interfaces import Job
from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.vector_store import QdrantVectorStore


@pytest.mark.asyncio
async def test_repeated_generate_embeddings_converges_to_stable_qdrant_points(
    real_db_session_factory, real_qdrant_test_collection
):
    qdrant_client, collection_name = real_qdrant_test_collection

    user_id = uuid4()
    doc_id = uuid4()
    chunk_1_id = uuid4()
    chunk_2_id = uuid4()

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"emb_user_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="emb_doc.txt",
                original_filename="emb_doc.txt",
                content_type="text/plain",
                file_size=100,
                checksum="abc123sha",
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.COMPLETED.value,
            )
        )
        session.add(
            SQLAlchemyChunk(
                id=chunk_1_id,
                document_id=doc_id,
                chunk_index=0,
                text="Idempotent embedding test paragraph 1.",
                character_start=0,
                character_end=37,
                token_estimate=6,
            )
        )
        session.add(
            SQLAlchemyChunk(
                id=chunk_2_id,
                document_id=doc_id,
                chunk_index=1,
                text="Idempotent embedding test paragraph 2.",
                character_start=38,
                character_end=75,
                token_estimate=6,
            )
        )
        await session.commit()

    # Deterministic vector generator mock (returns 1536 float vectors)
    mock_generator = AsyncMock()
    mock_generator.batch_generate = AsyncMock(
        return_value=[[0.01 * (i + 1)] * 1536 for i in range(2)]
    )

    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        dimension=1536,
    )

    handler = GenerateEmbeddingsJobHandler(
        db_session_factory=real_db_session_factory,
        embedding_generator=mock_generator,
        vector_store=vector_store,
    )

    job = Job(
        task_type="GENERATE_EMBEDDINGS",
        payload={"document_id": str(doc_id), "user_id": str(user_id)},
    )

    # 1. First execution
    res1 = await handler.handle(job)
    assert res1.success is True

    # Verify Qdrant points count
    count1 = await qdrant_client.count(collection_name=collection_name)
    assert count1.count == 2

    # 2. Re-execution of identical job (at-least-once replay)
    res2 = await handler.handle(job)
    assert res2.success is True

    # Verify Qdrant points count remains strictly 2 (no duplicate vector points)
    count2 = await qdrant_client.count(collection_name=collection_name)
    assert count2.count == 2

    # Verify points exist with chunk_id IDs
    points = await qdrant_client.retrieve(
        collection_name=collection_name,
        ids=[str(chunk_1_id), str(chunk_2_id)],
    )
    assert len(points) == 2


@pytest.mark.asyncio
async def test_partial_embedding_failure_retry_converges_without_duplicates(
    real_db_session_factory, real_qdrant_test_collection
):
    qdrant_client, collection_name = real_qdrant_test_collection

    user_id = uuid4()
    doc_id = uuid4()
    chunk_1_id = uuid4()
    chunk_2_id = uuid4()

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"emb_part_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="emb_part.txt",
                original_filename="emb_part.txt",
                content_type="text/plain",
                file_size=100,
                checksum="abc456sha",
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.COMPLETED.value,
            )
        )
        session.add(
            SQLAlchemyChunk(
                id=chunk_1_id,
                document_id=doc_id,
                chunk_index=0,
                text="Chunk one content",
                character_start=0,
                character_end=17,
                token_estimate=3,
            )
        )
        session.add(
            SQLAlchemyChunk(
                id=chunk_2_id,
                document_id=doc_id,
                chunk_index=1,
                text="Chunk two content",
                character_start=18,
                character_end=35,
                token_estimate=3,
            )
        )
        await session.commit()

    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        dimension=1536,
    )

    call_count = 0

    async def flaky_batch_generate(texts):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate transient timeout on first attempt
            raise TimeoutError("Simulated upstream provider timeout")
        return [[0.05] * 1536 for _ in texts]

    mock_flaky_generator = AsyncMock()
    mock_flaky_generator.batch_generate.side_effect = flaky_batch_generate

    handler = GenerateEmbeddingsJobHandler(
        db_session_factory=real_db_session_factory,
        embedding_generator=mock_flaky_generator,
        vector_store=vector_store,
    )

    job = Job(
        task_type="GENERATE_EMBEDDINGS",
        payload={"document_id": str(doc_id), "user_id": str(user_id)},
    )

    # 1. Attempt 1 fails
    res1 = await handler.handle(job)
    assert res1.success is False
    assert res1.retryable is True

    # 2. Attempt 2 succeeds
    job.attempt = 2
    res2 = await handler.handle(job)
    assert res2.success is True

    # Final Qdrant collection state has exactly 2 points
    count = await qdrant_client.count(collection_name=collection_name)
    assert count.count == 2
