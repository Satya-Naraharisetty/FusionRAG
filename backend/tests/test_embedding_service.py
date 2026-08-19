from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.documents.domain.models import (
    Chunk,
    Document,
    DocumentStatus,
    EmbeddingStatus,
)
from app.documents.services.embedding_service import EmbeddingService


class MockUnitOfWork:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_embedding_service_batch_success(mocker):
    generator = mocker.AsyncMock()
    generator.batch_generate.side_effect = lambda texts: [[0.1] * 768 for _ in texts]

    vector_store = mocker.AsyncMock()
    embedding_repo = mocker.AsyncMock()
    embedding_repo.list_by_document.return_value = []
    embedding_repo.get_by_chunk.return_value = None
    embedding_repo.get_by_chunk_ids.return_value = []

    chunk_repo = mocker.AsyncMock()
    doc_id = uuid4()
    chunks = [
        Chunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=i,
            text=f"chunk {i}",
            character_start=0,
            character_end=10,
            token_estimate=2,
            created_at=datetime.now(UTC),
        )
        for i in range(5)
    ]
    chunk_repo.list_by_document.return_value = chunks

    document_repo = mocker.AsyncMock()
    document = Document(
        id=doc_id,
        user_id=uuid4(),
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=100,
        checksum="hash",
        status=DocumentStatus.COMPLETED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    document_repo.get_by_id.return_value = document

    uow = MockUnitOfWork()

    time_provider = mocker.MagicMock()
    time_provider.get_now.return_value = datetime.now(UTC)

    uuid_generator = mocker.MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()

    service = EmbeddingService(
        embedding_generator=generator,
        vector_store=vector_store,
        embedding_repo=embedding_repo,
        chunk_repo=chunk_repo,
        document_repo=document_repo,
        uow=uow,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        batch_size=2,
        provider_name="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding_version="v1",
    )

    await service.generate_embeddings(doc_id)

    assert generator.batch_generate.call_count == 3
    assert vector_store.upsert.call_count == 3
    assert embedding_repo.save.call_count == 10  # 5 for GENERATING, 5 for COMPLETED


@pytest.mark.asyncio
async def test_embedding_service_batch_failure_isolation(mocker):
    generator = mocker.AsyncMock()

    # Batch 1 (0, 1) succeeds, Batch 2 (2, 3) fails, Batch 3 (4) succeeds
    async def mock_batch_generate(texts):
        if "chunk 2" in texts or "chunk 3" in texts:
            raise RuntimeError("Gemini API limit exceeded")
        return [[0.1] * 768 for _ in texts]

    generator.batch_generate.side_effect = mock_batch_generate

    vector_store = mocker.AsyncMock()
    embedding_repo = mocker.AsyncMock()
    embedding_repo.list_by_document.return_value = []
    embedding_repo.get_by_chunk.return_value = None
    embedding_repo.get_by_chunk_ids.return_value = []

    chunk_repo = mocker.AsyncMock()
    doc_id = uuid4()
    chunks = [
        Chunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=i,
            text=f"chunk {i}",
            character_start=0,
            character_end=10,
            token_estimate=2,
            created_at=datetime.now(UTC),
        )
        for i in range(5)
    ]
    chunk_repo.list_by_document.return_value = chunks

    document_repo = mocker.AsyncMock()
    document = Document(
        id=doc_id,
        user_id=uuid4(),
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=100,
        checksum="hash",
        status=DocumentStatus.COMPLETED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    document_repo.get_by_id.return_value = document

    uow = MockUnitOfWork()

    time_provider = mocker.MagicMock()
    time_provider.get_now.return_value = datetime.now(UTC)

    uuid_generator = mocker.MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()

    service = EmbeddingService(
        embedding_generator=generator,
        vector_store=vector_store,
        embedding_repo=embedding_repo,
        chunk_repo=chunk_repo,
        document_repo=document_repo,
        uow=uow,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        batch_size=2,
        provider_name="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding_version="v1",
    )

    await service.generate_embeddings(doc_id)

    # Gather saved embedding records from repo mock
    saved_embeddings = [call[0][0] for call in embedding_repo.save.call_args_list]

    completed_ids = [
        emb.chunk_id
        for emb in saved_embeddings
        if emb.status == EmbeddingStatus.COMPLETED
    ]
    failed_ids = [
        emb.chunk_id for emb in saved_embeddings if emb.status == EmbeddingStatus.FAILED
    ]

    # Batch 1 (0, 1) and Batch 3 (4) should be COMPLETED
    assert chunks[0].id in completed_ids
    assert chunks[1].id in completed_ids
    assert chunks[4].id in completed_ids

    # Batch 2 (2, 3) should be FAILED
    assert chunks[2].id in failed_ids
    assert chunks[3].id in failed_ids


@pytest.mark.asyncio
async def test_embedding_service_batch_no_n_plus_1(mocker):
    generator = mocker.AsyncMock()
    generator.batch_generate.side_effect = lambda texts: [[0.1] * 768 for _ in texts]

    vector_store = mocker.AsyncMock()
    embedding_repo = mocker.AsyncMock()
    embedding_repo.list_by_document.return_value = []
    embedding_repo.get_by_chunk_ids.return_value = []

    # get_by_chunk has side_effect raise AssertionError
    async def raise_assert(*args, **kwargs):
        raise AssertionError("get_by_chunk was called! Expected N+1 query elimination.")

    embedding_repo.get_by_chunk.side_effect = raise_assert

    chunk_repo = mocker.AsyncMock()
    doc_id = uuid4()
    chunks = [
        Chunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=i,
            text=f"chunk {i}",
            character_start=0,
            character_end=10,
            token_estimate=2,
            created_at=datetime.now(UTC),
        )
        for i in range(5)
    ]
    chunk_repo.list_by_document.return_value = chunks

    document_repo = mocker.AsyncMock()
    document = Document(
        id=doc_id,
        user_id=uuid4(),
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=100,
        checksum="hash",
        status=DocumentStatus.COMPLETED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    document_repo.get_by_id.return_value = document

    uow = MockUnitOfWork()
    time_provider = mocker.MagicMock()
    time_provider.get_now.return_value = datetime.now(UTC)
    uuid_generator = mocker.MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()

    service = EmbeddingService(
        embedding_generator=generator,
        vector_store=vector_store,
        embedding_repo=embedding_repo,
        chunk_repo=chunk_repo,
        document_repo=document_repo,
        uow=uow,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        batch_size=2,
        provider_name="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding_version="v1",
    )

    await service.generate_embeddings(doc_id)

    # Verify that get_by_chunk was never called
    embedding_repo.get_by_chunk.assert_not_called()
    # Verify that get_by_chunk_ids was called to batch fetch statuses
    assert embedding_repo.get_by_chunk_ids.call_count > 0
