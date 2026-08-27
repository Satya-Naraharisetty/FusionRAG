from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.queue.handlers import ProcessDocumentJobHandler
from app.core.queue.interfaces import Job
from app.documents.domain.models import DocumentScope, DocumentStatus, EmbeddingStatus
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
    SQLAlchemyEmbedding,
)


@pytest.mark.asyncio
async def test_downstream_enqueue_failure_propagates_retryable():
    """
    Case 1: If enqueueing GENERATE_EMBEDDINGS fails after chunking, the handler
    must NOT return success=True; it must return success=False, retryable=True.
    """
    user_id = uuid4()
    doc_id = uuid4()

    doc = SQLAlchemyDocument(
        id=doc_id,
        user_id=user_id,
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=50,
        checksum="chk_123",
        scope=DocumentScope.LIBRARY.value,
        status=DocumentStatus.QUEUED.value,
    )

    # Mock session and repositories
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.close = AsyncMock()

    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_session_factory.return_value = mock_session_ctx

    # Mock doc repository
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = doc

    # Mock storage and extractor
    mock_storage = AsyncMock()
    mock_storage.load.return_value = b"Hello world quantum computing."
    mock_extractor_factory = AsyncMock()
    mock_extractor = AsyncMock()
    mock_extractor.extract.return_value = MagicMock(
        text="Hello world quantum computing."
    )
    mock_extractor_factory.get_extractor.return_value = mock_extractor

    # Mock task queue whose enqueue raises ConnectionError
    mock_queue = AsyncMock()
    mock_queue.enqueue.side_effect = ConnectionError("Redis cluster unreachable")

    handler = ProcessDocumentJobHandler(
        db_session_factory=mock_session_factory,
        storage_provider=mock_storage,
        extractor_factory=mock_extractor_factory,
        task_queue=mock_queue,
    )

    # Patch SQLAlchemyDocumentRepository inside handle
    from unittest.mock import patch

    with (
        patch(
            "app.core.queue.handlers.SQLAlchemyDocumentRepository",
            return_value=mock_doc_repo,
        ),
        patch(
            "app.core.queue.handlers.DocumentProcessingService.process_document",
            new_callable=AsyncMock,
        ),
    ):
        job = Job(
            job_id=uuid4(),
            task_type="PROCESS_DOCUMENT",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )

        result = await handler.handle(job)

        # Invariant: Must return retryable failure
        assert result.success is False
        assert result.retryable is True
        assert "Failed to enqueue downstream GENERATE_EMBEDDINGS" in result.error


@pytest.mark.asyncio
async def test_completed_document_recovers_missing_embeddings():
    """
    Case 2: If a document is already COMPLETED in PostgreSQL but missing embeddings,
    re-running the handler must detect missing embeddings and enqueue GENERATE_EMBEDDINGS.
    """
    user_id = uuid4()
    doc_id = uuid4()
    chunk_id = uuid4()

    doc = SQLAlchemyDocument(
        id=doc_id,
        user_id=user_id,
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=50,
        checksum="chk_123",
        scope=DocumentScope.LIBRARY.value,
        status=DocumentStatus.COMPLETED.value,
    )
    chunk = SQLAlchemyChunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=0,
        text="Chunk text",
        character_start=0,
        character_end=10,
        token_estimate=2,
    )

    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_session_factory.return_value = mock_session_ctx

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = doc

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.list_by_document.return_value = [chunk]

    mock_emb_repo = AsyncMock()
    mock_emb_repo.get_by_chunk_ids.return_value = []  # 0 embeddings

    mock_queue = AsyncMock()
    mock_queue.enqueue.return_value = "msg_123"

    handler = ProcessDocumentJobHandler(
        db_session_factory=mock_session_factory,
        task_queue=mock_queue,
    )

    from unittest.mock import patch

    with (
        patch(
            "app.core.queue.handlers.SQLAlchemyDocumentRepository",
            return_value=mock_doc_repo,
        ),
        patch(
            "app.core.queue.handlers.SQLAlchemyChunkRepository",
            return_value=mock_chunk_repo,
        ),
        patch(
            "app.core.queue.handlers.SQLAlchemyEmbeddingRepository",
            return_value=mock_emb_repo,
        ),
    ):
        job = Job(
            job_id=uuid4(),
            task_type="PROCESS_DOCUMENT",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )

        result = await handler.handle(job)

        # Must detect missing embeddings and enqueue GENERATE_EMBEDDINGS
        assert result.success is True
        assert result.details.get("embeddings") == "enqueued"
        mock_queue.enqueue.assert_called_once_with(
            task_type="GENERATE_EMBEDDINGS",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
            max_attempts=3,
        )


@pytest.mark.asyncio
async def test_completed_document_verifies_all_embeddings_complete():
    """
    Case 3: If all expected chunks have COMPLETED embeddings, handler skips
    downstream enqueue and returns verified_complete.
    """
    user_id = uuid4()
    doc_id = uuid4()
    chunk_1 = uuid4()
    chunk_2 = uuid4()

    doc = SQLAlchemyDocument(
        id=doc_id,
        user_id=user_id,
        filename="test.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=50,
        checksum="chk_123",
        scope=DocumentScope.LIBRARY.value,
        status=DocumentStatus.COMPLETED.value,
    )
    chunks = [
        SQLAlchemyChunk(
            id=chunk_1,
            document_id=doc_id,
            chunk_index=0,
            text="Chunk 1",
            character_start=0,
            character_end=7,
            token_estimate=2,
        ),
        SQLAlchemyChunk(
            id=chunk_2,
            document_id=doc_id,
            chunk_index=1,
            text="Chunk 2",
            character_start=8,
            character_end=15,
            token_estimate=2,
        ),
    ]
    embeddings = [
        SQLAlchemyEmbedding(
            id=uuid4(),
            chunk_id=chunk_1,
            status=EmbeddingStatus.COMPLETED,
            embedding_model="m1",
        ),
        SQLAlchemyEmbedding(
            id=uuid4(),
            chunk_id=chunk_2,
            status=EmbeddingStatus.COMPLETED,
            embedding_model="m1",
        ),
    ]

    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_session_factory.return_value = mock_session_ctx

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = doc

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.list_by_document.return_value = chunks

    mock_emb_repo = AsyncMock()
    mock_emb_repo.get_by_chunk_ids.return_value = embeddings

    mock_queue = AsyncMock()

    handler = ProcessDocumentJobHandler(
        db_session_factory=mock_session_factory,
        task_queue=mock_queue,
    )

    from unittest.mock import patch

    with (
        patch(
            "app.core.queue.handlers.SQLAlchemyDocumentRepository",
            return_value=mock_doc_repo,
        ),
        patch(
            "app.core.queue.handlers.SQLAlchemyChunkRepository",
            return_value=mock_chunk_repo,
        ),
        patch(
            "app.core.queue.handlers.SQLAlchemyEmbeddingRepository",
            return_value=mock_emb_repo,
        ),
    ):
        job = Job(
            job_id=uuid4(),
            task_type="PROCESS_DOCUMENT",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )

        result = await handler.handle(job)

        assert result.success is True
        assert result.details.get("embeddings") == "verified_complete"
        # No extra enqueue needed
        mock_queue.enqueue.assert_not_called()
