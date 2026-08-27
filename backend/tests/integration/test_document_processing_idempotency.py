import uuid
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.core.queue.handlers import ProcessDocumentJobHandler
from app.core.queue.interfaces import Job
from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.repositories.document_repository import (
    SQLAlchemyDocumentRepository,
)
from app.documents.infrastructure.storage import LocalStorageProvider


@pytest.mark.asyncio
async def test_duplicate_process_document_job_is_strictly_idempotent(
    real_db_session_factory, tmp_path
):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_provider = LocalStorageProvider(upload_dir=str(storage_dir))
    extractor_factory = ExtractorFactory()

    handler = ProcessDocumentJobHandler(
        db_session_factory=real_db_session_factory,
        storage_provider=storage_provider,
        extractor_factory=extractor_factory,
    )

    doc_id = uuid4()
    user_id = uuid4()
    content = (
        b"This is idempotent document testing content for processing verification."
    )
    stored_path = await storage_provider.save(
        filename="idempotent_test.txt",
        content=content,
        user_id=user_id,
        document_id=doc_id,
    )

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"idemp_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename=stored_path,
                original_filename="idempotent_test.txt",
                content_type="text/plain",
                file_size=len(content),
                checksum="dummy_sha256",
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.QUEUED.value,
            )
        )
        await session.commit()

    job = Job(
        task_type="PROCESS_DOCUMENT",
        payload={"document_id": str(doc_id), "user_id": str(user_id)},
    )

    # 1. First execution
    result1 = await handler.handle(job)
    assert result1.success is True

    async with real_db_session_factory() as session:
        chunks_run1 = (
            (
                await session.execute(
                    select(SQLAlchemyChunk).where(SQLAlchemyChunk.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
        chunk_count_1 = len(chunks_run1)
        assert chunk_count_1 > 0
        chunk_ids_1 = [c.id for c in chunks_run1]

        doc_repo = SQLAlchemyDocumentRepository(session)
        doc_1 = await doc_repo.get_by_id(doc_id)
        assert doc_1.status == DocumentStatus.COMPLETED

    # 2. Duplicate execution of identical job (simulating retry / at-least-once replay)
    result2 = await handler.handle(job)
    assert result2.success is True

    async with real_db_session_factory() as session:
        chunks_run2 = (
            (
                await session.execute(
                    select(SQLAlchemyChunk).where(SQLAlchemyChunk.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
        chunk_count_2 = len(chunks_run2)
        chunk_ids_2 = [c.id for c in chunks_run2]

        assert chunk_count_2 == chunk_count_1
        assert chunk_ids_2 == chunk_ids_1


@pytest.mark.asyncio
async def test_version_aware_chunk_id_isolation_between_versions(
    real_db_session_factory, tmp_path
):
    """
    Verifies that chunk UUIDs generated with uuid5(document_id, f'{checksum}:{chunk_index}')
    guarantee non-collision across versions.
    """
    doc_id = uuid4()
    checksum_v1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    checksum_v2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    # Same chunk index across different versions
    chunk_0_v1_id = uuid.uuid5(doc_id, f"{checksum_v1}:0")
    chunk_0_v2_id = uuid.uuid5(doc_id, f"{checksum_v2}:0")

    assert chunk_0_v1_id != chunk_0_v2_id

    # Same version produces exactly the identical ID
    chunk_0_v1_repeat = uuid.uuid5(doc_id, f"{checksum_v1}:0")
    assert chunk_0_v1_id == chunk_0_v1_repeat
