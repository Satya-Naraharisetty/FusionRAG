import hashlib
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.core.queue.handlers import (
    GenerateEmbeddingsJobHandler,
    ProcessDocumentJobHandler,
)
from app.core.queue.interfaces import Job
from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.vector_store import QdrantVectorStore
from app.documents.infrastructure.storage import LocalStorageProvider
from app.documents.services.postgres_sparse_retriever import PostgresSparseRetriever


@pytest.mark.asyncio
async def test_end_to_end_document_replacement_lifecycle(
    real_db_session_factory, real_qdrant_test_collection, tmp_path
):
    qdrant_client, collection_name = real_qdrant_test_collection
    storage_dir = tmp_path / "storage_repl"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_provider = LocalStorageProvider(upload_dir=str(storage_dir))
    extractor_factory = ExtractorFactory()

    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        dimension=1536,
    )

    user_id = uuid4()
    doc_id = uuid4()

    # Create user
    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"replace_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        await session.commit()

    # Step 1: Ingest Version 1
    content_v1 = b"Architecture Alpha: Monolithic relational database system with ACID properties."
    checksum_v1 = hashlib.sha256(content_v1).hexdigest()
    path_v1 = await storage_provider.save(
        filename="system_arch.txt",
        content=content_v1,
        user_id=user_id,
        document_id=doc_id,
    )

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_id,
                filename=path_v1,
                original_filename="system_arch.txt",
                content_type="text/plain",
                file_size=len(content_v1),
                checksum=checksum_v1,
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.QUEUED.value,
            )
        )
        await session.commit()

    # Process V1
    proc_handler = ProcessDocumentJobHandler(
        db_session_factory=real_db_session_factory,
        storage_provider=storage_provider,
        extractor_factory=extractor_factory,
    )
    res_proc_1 = await proc_handler.handle(
        Job(task_type="PROCESS_DOCUMENT", payload={"document_id": str(doc_id), "user_id": str(user_id)})
    )
    assert res_proc_1.success is True

    # Embed V1
    mock_gen_v1 = AsyncMock()
    mock_gen_v1.batch_generate = AsyncMock(return_value=[[0.1] * 1536])
    emb_handler = GenerateEmbeddingsJobHandler(
        db_session_factory=real_db_session_factory,
        embedding_generator=mock_gen_v1,
        vector_store=vector_store,
    )
    res_emb_1 = await emb_handler.handle(
        Job(task_type="GENERATE_EMBEDDINGS", payload={"document_id": str(doc_id), "user_id": str(user_id)})
    )
    assert res_emb_1.success is True

    # Verify V1 in sparse search
    async with real_db_session_factory() as session:
        retriever = PostgresSparseRetriever(db=session)
        sparse_v1 = await retriever.search(
            query="Monolithic relational database",
            user_id=user_id,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(sparse_v1) == 1
        assert "Monolithic" in sparse_v1[0].text

    # Verify V1 points count in Qdrant
    q_count_1 = await qdrant_client.count(collection_name=collection_name)
    assert q_count_1.count == 1

    # Step 2: Replace with Version 2
    content_v2 = b"Architecture Beta: Event-driven distributed microservices streaming platform."
    checksum_v2 = hashlib.sha256(content_v2).hexdigest()
    path_v2 = await storage_provider.save(
        filename="system_arch.txt",
        content=content_v2,
        user_id=user_id,
        document_id=doc_id,
    )

    async with real_db_session_factory() as session:
        # Update document record to V2
        doc_orm = (
            await session.execute(select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == doc_id))
        ).scalar_one()
        doc_orm.checksum = checksum_v2
        doc_orm.filename = path_v2
        doc_orm.file_size = len(content_v2)
        doc_orm.status = DocumentStatus.QUEUED.value
        await session.commit()

    # Process V2
    res_proc_2 = await proc_handler.handle(
        Job(task_type="PROCESS_DOCUMENT", payload={"document_id": str(doc_id), "user_id": str(user_id)})
    )
    assert res_proc_2.success is True

    # Embed V2 (with force=True or for replaced chunks)
    mock_gen_v2 = AsyncMock()
    mock_gen_v2.batch_generate = AsyncMock(return_value=[[0.9] * 1536])
    emb_handler_v2 = GenerateEmbeddingsJobHandler(
        db_session_factory=real_db_session_factory,
        embedding_generator=mock_gen_v2,
        vector_store=vector_store,
    )
    res_emb_2 = await emb_handler_v2.handle(
        Job(
            task_type="GENERATE_EMBEDDINGS",
            payload={"document_id": str(doc_id), "user_id": str(user_id), "force": True},
        )
    )
    assert res_emb_2.success is True

    # Step 3: Verify Search Results after replacement
    async with real_db_session_factory() as session:
        retriever = PostgresSparseRetriever(db=session)

        # Old V1 term is gone
        sparse_old = await retriever.search(
            query="Monolithic relational database",
            user_id=user_id,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(sparse_old) == 0

        # New V2 term is present
        sparse_new = await retriever.search(
            query="Event-driven distributed microservices",
            user_id=user_id,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(sparse_new) == 1
        assert "microservices streaming" in sparse_new[0].text
