from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.services.postgres_sparse_retriever import PostgresSparseRetriever


@pytest.mark.asyncio
async def test_multi_worker_sparse_search_realtime_consistency(real_db_session_factory):
    user_a = uuid4()
    user_b = uuid4()
    doc_id = uuid4()
    chunk_id = uuid4()

    # Setup users
    async with real_db_session_factory() as session_setup:
        session_setup.add(
            SQLAlchemyUser(
                id=user_a,
                email=f"worker_a_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session_setup.add(
            SQLAlchemyUser(
                id=user_b,
                email=f"worker_b_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        await session_setup.commit()

    # 1. Worker A creates document and chunk
    async with real_db_session_factory() as session_worker_a:
        session_worker_a.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_a,
                filename="quantum_paper.txt",
                original_filename="quantum_paper.txt",
                content_type="text/plain",
                file_size=120,
                checksum="checksum_v1",
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.COMPLETED.value,
            )
        )
        session_worker_a.add(
            SQLAlchemyChunk(
                id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Superconducting qubits and quantum computation algorithms.",
                character_start=0,
                character_end=58,
                token_estimate=8,
            )
        )
        await session_worker_a.commit()

    # 2. Worker B immediately searches for "quantum computation"
    async with real_db_session_factory() as session_worker_b:
        retriever_b = PostgresSparseRetriever(db=session_worker_b)
        results = await retriever_b.search(
            query="quantum computation",
            user_id=user_a,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(results) == 1
        assert results[0].chunk_id == chunk_id
        assert "quantum computation" in results[0].text

    # 3. Worker A replaces document content (Version 2)
    async with real_db_session_factory() as session_worker_a:
        # Delete old chunk and insert new chunk
        await session_worker_a.execute(
            delete(SQLAlchemyChunk).where(SQLAlchemyChunk.document_id == doc_id)
        )
        new_chunk_id = uuid4()
        session_worker_a.add(
            SQLAlchemyChunk(
                id=new_chunk_id,
                document_id=doc_id,
                chunk_index=0,
                text="Relativity astrophysics and gravitation near black holes.",
                character_start=0,
                character_end=57,
                token_estimate=8,
            )
        )
        await session_worker_a.commit()

    # 4. Worker B searches again: old terms should be gone, new terms visible
    async with real_db_session_factory() as session_worker_b:
        retriever_b = PostgresSparseRetriever(db=session_worker_b)

        # Old query returns 0
        old_res = await retriever_b.search(
            query="quantum computation",
            user_id=user_a,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(old_res) == 0

        # New query returns new chunk
        new_res = await retriever_b.search(
            query="astrophysics black holes",
            user_id=user_a,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(new_res) == 1
        assert new_res[0].chunk_id == new_chunk_id

    # 5. Worker A deletes the document
    async with real_db_session_factory() as session_worker_a:
        await session_worker_a.execute(
            delete(SQLAlchemyDocument).where(SQLAlchemyDocument.id == doc_id)
        )
        await session_worker_a.commit()

    # 6. Worker B searches again: should return 0 results
    async with real_db_session_factory() as session_worker_b:
        retriever_b = PostgresSparseRetriever(db=session_worker_b)
        deleted_res = await retriever_b.search(
            query="astrophysics black holes",
            user_id=user_a,
            top_k=5,
            document_ids=[doc_id],
        )
        assert len(deleted_res) == 0


@pytest.mark.asyncio
async def test_multi_worker_sparse_search_cross_user_isolation(real_db_session_factory):
    user_1 = uuid4()
    user_2 = uuid4()
    doc_id = uuid4()

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_1,
                email=f"u1_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            SQLAlchemyUser(
                id=user_2,
                email=f"u2_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            SQLAlchemyDocument(
                id=doc_id,
                user_id=user_1,
                filename="confidential.txt",
                original_filename="confidential.txt",
                content_type="text/plain",
                file_size=50,
                checksum="chk_conf",
                scope=DocumentScope.LIBRARY.value,
                status=DocumentStatus.COMPLETED.value,
            )
        )
        session.add(
            SQLAlchemyChunk(
                id=uuid4(),
                document_id=doc_id,
                chunk_index=0,
                text="Top secret proprietary enterprise trade secret algorithms.",
                character_start=0,
                character_end=58,
                token_estimate=7,
            )
        )
        await session.commit()

    # User 2 searches for trade secrets -> isolation must prevent seeing User 1's doc
    async with real_db_session_factory() as session:
        retriever = PostgresSparseRetriever(db=session)
        res = await retriever.search(
            query="enterprise trade secret",
            user_id=user_2,
            top_k=10,
        )
        assert len(res) == 0
