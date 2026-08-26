import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import app.api.v1.documents as docs_module
from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.auth.infrastructure.providers import (
    SQLAlchemyUnitOfWork,
    SystemTimeProvider,
    SystemUUIDGenerator,
)
from app.chat.infrastructure.persistence.models import (
    ConversationMessageORM,
    ConversationORM,
)
from app.core.queue import (
    GenerateEmbeddingsJobHandler,
    InMemoryDurableTaskQueue,
    Job,
    JobDispatcher,
    ProcessDocumentJobHandler,
    SummarizeConversationJobHandler,
)
from app.db.models import Base
from app.documents.domain.interfaces import StorageProvider
from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.infrastructure.persistence.repositories.document_repository import (
    SQLAlchemyDocumentRepository,
)
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.document_service import DocumentService
from app.documents.services.embedding_service import EmbeddingService
from tests.db import TEST_DATABASE_URL


class InMemoryStorageProvider(StorageProvider):
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(
        self, filename: str, content: bytes, user_id: Any, document_id: Any
    ) -> str:
        key = f"{user_id}/{document_id}/{filename}"
        self.files[key] = content
        return key

    async def get(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(f"File not found: {key}")
        return self.files[key]

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://mock-storage.local/{key}"

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://mock-storage.local/{key}"


def _sync_setup_db(sync_engine):
    Base.metadata.create_all(bind=sync_engine)
    sync_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=sync_engine
    )
    db = sync_session_local()
    try:
        db.execute(text("DELETE FROM document_embeddings;"))
        db.execute(text("DELETE FROM document_chunks;"))
        db.execute(text("DELETE FROM documents;"))
        db.execute(text("DELETE FROM conversation_summaries;"))
        db.execute(text("DELETE FROM conversation_messages;"))
        db.execute(text("DELETE FROM conversations;"))
        db.execute(text("DELETE FROM refresh_sessions;"))
        db.execute(text("DELETE FROM users;"))
        db.execute(
            text(
                "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector "
                "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;"
            )
        )
        db.commit()
    finally:
        db.close()
    sync_engine.dispose()


@pytest.fixture(scope="function")
def postgres_test_db():
    sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(async_url, poolclass=NullPool)
    try:
        _sync_setup_db(sync_engine)
        session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        yield session_factory
    finally:
        async_engine.sync_engine.dispose()


@pytest.mark.asyncio
async def test_upload_enqueues_durable_job(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="upload_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.commit()

        durable_queue = InMemoryDurableTaskQueue()
        storage = InMemoryStorageProvider()
        extractor_factory = ExtractorFactory()
        checksum_gen = SHA256ChecksumGenerator()

        doc_service = DocumentService(
            document_repo=SQLAlchemyDocumentRepository(session),
            storage_provider=storage,
            extractor_factory=extractor_factory,
            checksum_generator=checksum_gen,
            task_queue=durable_queue,
            document_processing_service=MagicMock(spec=DocumentProcessingService),
            embedding_service=MagicMock(spec=EmbeddingService),
            uow=SQLAlchemyUnitOfWork(session),
            uuid_generator=SystemUUIDGenerator(),
            time_provider=SystemTimeProvider(),
            max_upload_size=1024 * 1024,
        )

        doc = await doc_service.upload_document(
            original_filename="sample.txt",
            content_type="text/plain",
            file_bytes=b"Durable task queue processing test content.",
            user_id=user_id,
            scope=DocumentScope.LIBRARY,
        )

        assert doc.status == DocumentStatus.QUEUED
        assert len(durable_queue.jobs) == 1
        queued_job = list(durable_queue.jobs.values())[0]
        assert queued_job.task_type == "PROCESS_DOCUMENT"
        assert queued_job.payload["document_id"] == str(doc.id)
        assert queued_job.payload["user_id"] == str(user_id)
        assert queued_job.payload["scope"] == "LIBRARY"
        # Ensure no raw bytes were placed in the job payload
        assert "file_bytes" not in queued_job.payload
        assert "raw_bytes" not in queued_job.payload


@pytest.mark.asyncio
async def test_replace_enqueues_durable_job(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="replace_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        doc_id = uuid4()
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="initial.txt",
                original_filename="initial.txt",
                content_type="text/plain",
                file_size=10,
                checksum="oldchecksum123",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.commit()

        durable_queue = InMemoryDurableTaskQueue()
        storage = InMemoryStorageProvider()
        extractor_factory = ExtractorFactory()
        checksum_gen = SHA256ChecksumGenerator()

        doc_service = DocumentService(
            document_repo=SQLAlchemyDocumentRepository(session),
            storage_provider=storage,
            extractor_factory=extractor_factory,
            checksum_generator=checksum_gen,
            task_queue=durable_queue,
            document_processing_service=MagicMock(spec=DocumentProcessingService),
            embedding_service=MagicMock(spec=EmbeddingService),
            uow=SQLAlchemyUnitOfWork(session),
            uuid_generator=SystemUUIDGenerator(),
            time_provider=SystemTimeProvider(),
            max_upload_size=1024 * 1024,
        )

        updated_doc = await doc_service.replace_document_content(
            id=doc_id,
            user_id=user_id,
            file_bytes=b"Replaced content with brand new text.",
            original_filename="initial.txt",
            content_type="text/plain",
        )

        assert updated_doc.status == DocumentStatus.QUEUED
        assert len(durable_queue.jobs) == 1
        assert list(durable_queue.jobs.values())[0].task_type == "PROCESS_DOCUMENT"
        assert list(durable_queue.jobs.values())[0].payload["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_reprocess_enqueues_durable_job(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="reprocess_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        doc_id = uuid4()
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="reprocess.txt",
                original_filename="reprocess.txt",
                content_type="text/plain",
                file_size=10,
                checksum="reprocesschk",
                status="failed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.commit()

        durable_queue = InMemoryDurableTaskQueue()
        storage = InMemoryStorageProvider()
        extractor_factory = ExtractorFactory()
        checksum_gen = SHA256ChecksumGenerator()

        doc_service = DocumentService(
            document_repo=SQLAlchemyDocumentRepository(session),
            storage_provider=storage,
            extractor_factory=extractor_factory,
            checksum_generator=checksum_gen,
            task_queue=durable_queue,
            document_processing_service=MagicMock(spec=DocumentProcessingService),
            embedding_service=MagicMock(spec=EmbeddingService),
            uow=SQLAlchemyUnitOfWork(session),
            uuid_generator=SystemUUIDGenerator(),
            time_provider=SystemTimeProvider(),
            max_upload_size=1024 * 1024,
        )

        reprocessed_doc = await doc_service.reprocess_document(id=doc_id, user_id=user_id)
        assert reprocessed_doc.status == DocumentStatus.QUEUED
        assert len(durable_queue.jobs) == 1
        assert list(durable_queue.jobs.values())[0].task_type == "PROCESS_DOCUMENT"
        assert list(durable_queue.jobs.values())[0].payload["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_process_document_handler_success_and_downstream_enqueue(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="handler_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        doc_id = uuid4()
        storage = InMemoryStorageProvider()
        storage_key = await storage.save(
            filename="handler.txt",
            content=b"Deep durable processing integration with PostgreSQL and Redis Streams.",
            user_id=user_id,
            document_id=doc_id,
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename=storage_key,
                original_filename="handler.txt",
                content_type="text/plain",
                file_size=50,
                checksum="handchk",
                status="queued",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.commit()

        durable_queue = InMemoryDurableTaskQueue()
        extractor_factory = ExtractorFactory()

        handler = ProcessDocumentJobHandler(
            db_session_factory=postgres_test_db,
            storage_provider=storage,
            extractor_factory=extractor_factory,
            task_queue=durable_queue,
        )

        job = Job(
            task_type="PROCESS_DOCUMENT",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )
        result = await handler.handle(job)

        assert result.success is True

        # Verify DB document transitioned to completed
        async with postgres_test_db() as check_session:
            doc_repo = SQLAlchemyDocumentRepository(check_session)
            doc = await doc_repo.get_by_id(doc_id)
            assert doc is not None
            assert doc.status == DocumentStatus.COMPLETED

            chunk_repo = SQLAlchemyChunkRepository(check_session)
            chunks = await chunk_repo.list_by_document(doc_id)
            assert len(chunks) >= 1

        # Verify downstream GENERATE_EMBEDDINGS job was enqueued
        assert len(durable_queue.jobs) == 1
        assert list(durable_queue.jobs.values())[0].task_type == "GENERATE_EMBEDDINGS"
        assert list(durable_queue.jobs.values())[0].payload["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_generate_embeddings_handler_success(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="embed_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        doc_id = uuid4()
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename="embed_doc.txt",
                original_filename="embed_doc.txt",
                content_type="text/plain",
                file_size=50,
                checksum="embedchk",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        chunk_id = uuid4()
        session.add(
            SQLAlchemyChunk(
                id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Vector embeddings generation test text chunk.",
                character_start=0,
                character_end=46,
                token_estimate=8,
                metadata_json={"document_scope": "LIBRARY"},
            )
        )
        await session.commit()

        mock_generator = MagicMock()
        mock_generator.batch_generate = AsyncMock(return_value=[[0.1] * 1536])
        mock_vector_store = MagicMock()
        mock_vector_store.upsert = AsyncMock()
        mock_vector_store.delete_document = AsyncMock()

        handler = GenerateEmbeddingsJobHandler(
            db_session_factory=postgres_test_db,
            embedding_generator=mock_generator,
            vector_store=mock_vector_store,
            batch_size=64,
        )

        job = Job(
            task_type="GENERATE_EMBEDDINGS",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )
        result = await handler.handle(job)

        assert result.success is True
        mock_generator.batch_generate.assert_called_once()
        mock_vector_store.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_process_document_job_is_idempotent(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="idemp_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        doc_id = uuid4()
        storage = InMemoryStorageProvider()
        storage_key = await storage.save(
            filename="idemp.txt",
            content=b"Idempotent document processing verification text.",
            user_id=user_id,
            document_id=doc_id,
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename=storage_key,
                original_filename="idemp.txt",
                content_type="text/plain",
                file_size=50,
                checksum="idempchk",
                status="queued",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.commit()

        extractor_factory = ExtractorFactory()
        handler = ProcessDocumentJobHandler(
            db_session_factory=postgres_test_db,
            storage_provider=storage,
            extractor_factory=extractor_factory,
            task_queue=None,
        )

        job = Job(
            task_type="PROCESS_DOCUMENT",
            payload={"document_id": str(doc_id), "user_id": str(user_id)},
        )

        # First execution
        res1 = await handler.handle(job)
        assert res1.success is True

        async with postgres_test_db() as s1:
            chunks1 = await SQLAlchemyChunkRepository(s1).list_by_document(doc_id)
            assert len(chunks1) >= 1
            chunk_ids_1 = [c.id for c in chunks1]

        # Second execution (simulating at-least-once redelivery)
        res2 = await handler.handle(job)
        assert res2.success is True

        async with postgres_test_db() as s2:
            chunks2 = await SQLAlchemyChunkRepository(s2).list_by_document(doc_id)
            assert len(chunks2) == len(chunks1)
            chunk_ids_2 = [c.id for c in chunks2]
            # Verify deterministic chunk IDs are completely identical across redeliveries
            assert chunk_ids_1 == chunk_ids_2


@pytest.mark.asyncio
async def test_job_references_deleted_document_handled_cleanly(postgres_test_db):
    missing_doc_id = uuid4()
    storage = InMemoryStorageProvider()
    extractor_factory = ExtractorFactory()

    handler = ProcessDocumentJobHandler(
        db_session_factory=postgres_test_db,
        storage_provider=storage,
        extractor_factory=extractor_factory,
    )

    job = Job(
        task_type="PROCESS_DOCUMENT",
        payload={"document_id": str(missing_doc_id)},
    )
    result = await handler.handle(job)

    assert result.success is False
    assert result.retryable is False
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_summarize_conversation_handler_below_threshold_is_skipped(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="sum_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        conv_id = uuid4()
        session.add(ConversationORM(id=conv_id, user_id=user_id, title="Test Conv"))
        msg_id = uuid4()
        session.add(
            ConversationMessageORM(
                id=msg_id,
                conversation_id=conv_id,
                role="user",
                content="Hello there!",
            )
        )
        await session.commit()

        mock_llm = MagicMock()
        handler = SummarizeConversationJobHandler(
            db_session_factory=postgres_test_db,
            llm_provider=mock_llm,
            model="gemini-2.5-flash",
            summary_trigger_messages=5,
        )

        job = Job(
            task_type="SUMMARIZE_CONVERSATION",
            payload={"conversation_id": str(conv_id), "message_id": str(msg_id)},
        )
        result = await handler.handle(job)

        assert result.success is True
        assert result.details.get("status") == "skipped_count_below_threshold"
        mock_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_summarize_conversation_handler_executes_summarizer(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="sum2_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        conv_id = uuid4()
        session.add(ConversationORM(id=conv_id, user_id=user_id, title="Active Chat"))
        for i in range(12):
            session.add(
                ConversationMessageORM(
                    id=uuid4(),
                    conversation_id=conv_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Message step {i} discussing durable architecture.",
                )
            )
        msg_id = uuid4()
        session.add(
            ConversationMessageORM(
                id=msg_id,
                conversation_id=conv_id,
                role="user",
                content="Triggering summarization threshold now.",
            )
        )
        await session.commit()

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=("Summary of conversation so far.", {"usage": {}})
        )
        handler = SummarizeConversationJobHandler(
            db_session_factory=postgres_test_db,
            llm_provider=mock_llm,
            model="gemini-2.5-flash",
            summary_trigger_messages=5,
            max_messages_per_context=10,
        )

        job = Job(
            task_type="SUMMARIZE_CONVERSATION",
            payload={"conversation_id": str(conv_id), "message_id": str(msg_id)},
        )
        result = await handler.handle(job)

        assert result.success is True
        assert result.details.get("status") == "summarized"
        mock_llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_worker_starts_and_stops_gracefully():
    from app.core.queue.worker import QueueWorker

    mock_queue = MagicMock()
    mock_queue.ensure_consumer_group = AsyncMock()
    mock_queue.read_messages = AsyncMock(return_value=[])
    mock_queue.retry_pump = AsyncMock()
    mock_queue.recover_orphans = AsyncMock()
    mock_queue.consumer_name = "test-worker-1"
    mock_queue.stream_name = "test_stream"
    mock_queue.consumer_group = "test_group"

    dispatcher = JobDispatcher()
    worker = QueueWorker(
        task_queue=mock_queue,
        dispatcher=dispatcher,
        concurrency=2,
    )

    await worker.start()
    assert worker.is_running is True

    await worker.stop(timeout_seconds=2.0)
    assert worker.is_running is False


def test_no_migrated_endpoint_uses_fastapi_background_tasks():
    """
    Verifies that all migrated endpoints in app.api.v1.documents do NOT take
    FastAPI / Starlette BackgroundTasks as parameters.
    """
    for name, obj in inspect.getmembers(docs_module):
        if inspect.iscoroutinefunction(obj):
            sig = inspect.signature(obj)
            param_names = list(sig.parameters.keys())
            assert "background_tasks" not in param_names, (
                f"Endpoint '{name}' still declares BackgroundTasks parameter: {param_names}"
            )
