from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.chat.infrastructure.persistence.models import ConversationORM
from app.db.models import Base
from app.documents.domain.models import DocumentRetrievalScope
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.services.postgres_sparse_retriever import PostgresSparseRetriever
from tests.db import TEST_DATABASE_URL


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
async def test_basic_keyword_retrieval(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        user = SQLAlchemyUser(
            id=user_id,
            email="test_user@example.com",
            hashed_password="hashed_pwd_123",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        doc_id = uuid4()
        doc = SQLAlchemyDocument(
            id=doc_id,
            user_id=user_id,
            filename="quantum.pdf",
            original_filename="quantum.pdf",
            content_type="application/pdf",
            file_size=1024,
            checksum="abc123chk",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        session.add(doc)
        await session.flush()

        chunk1 = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Quantum computing utilizes qubits for exponential speedup.",
            character_start=0,
            character_end=56,
            token_estimate=10,
            metadata_json={"document_scope": "LIBRARY"},
        )
        chunk2 = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Photosynthesis is the biological process of converting sunlight.",
            character_start=57,
            character_end=120,
            token_estimate=10,
            metadata_json={"document_scope": "LIBRARY"},
        )
        session.add_all([chunk1, chunk2])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
        results = await retriever.search(
            query="quantum qubits",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope,
        )

        assert len(results) == 1
        assert results[0].chunk_id == chunk1.id
        assert "Quantum" in results[0].text
        assert results[0].similarity_score > 0.0
        assert results[0].document_name == "quantum.pdf"


@pytest.mark.asyncio
async def test_multiple_matching_chunks_and_ranking(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="ranking_user@example.com",
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
                filename="ai_overview.txt",
                original_filename="ai_overview.txt",
                content_type="text/plain",
                file_size=500,
                checksum="chk2",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.flush()

        high_rel_chunk = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Deep learning networks and deep learning models require extensive training.",
            character_start=0,
            character_end=75,
            token_estimate=12,
            metadata_json={"document_scope": "LIBRARY"},
        )
        low_rel_chunk = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Machine learning is broad, while deep learning is a subset.",
            character_start=76,
            character_end=135,
            token_estimate=10,
            metadata_json={"document_scope": "LIBRARY"},
        )
        session.add_all([high_rel_chunk, low_rel_chunk])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
        results = await retriever.search(
            query="deep learning",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope,
        )

        assert len(results) == 2
        assert results[0].chunk_id == high_rel_chunk.id
        assert results[1].chunk_id == low_rel_chunk.id
        assert results[0].similarity_score >= results[1].similarity_score


@pytest.mark.asyncio
async def test_no_match_query_returns_empty(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="nomatch@example.com",
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
                filename="doc.txt",
                original_filename="doc.txt",
                content_type="text/plain",
                file_size=100,
                checksum="chk3",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.flush()

        session.add(
            SQLAlchemyChunk(
                id=uuid4(),
                document_id=doc_id,
                chunk_index=0,
                text="The quick brown fox jumps over the lazy dog.",
                character_start=0,
                character_end=44,
                token_estimate=9,
                metadata_json={"document_scope": "LIBRARY"},
            )
        )
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
        results = await retriever.search(
            query="quantum astrophysics supernova",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope,
        )

        assert results == []


@pytest.mark.asyncio
async def test_user_tenant_isolation(postgres_test_db):
    async with postgres_test_db() as session:
        user_a = uuid4()
        user_b = uuid4()

        session.add_all([
            SQLAlchemyUser(
                id=user_a,
                email="usera@example.com",
                hashed_password="pwd",
                is_active=True,
            ),
            SQLAlchemyUser(
                id=user_b,
                email="userb@example.com",
                hashed_password="pwd",
                is_active=True,
            ),
        ])
        await session.flush()

        doc_a = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_a,
            filename="user_a_doc.txt",
            original_filename="user_a_doc.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chka",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        doc_b = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_b,
            filename="user_b_doc.txt",
            original_filename="user_b_doc.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chkb",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        session.add_all([doc_a, doc_b])
        await session.flush()

        chunk_a = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_a.id,
            chunk_index=0,
            text="Confidential financial database records for User A.",
            character_start=0,
            character_end=51,
            token_estimate=8,
            metadata_json={"document_scope": "LIBRARY"},
        )
        chunk_b = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_b.id,
            chunk_index=0,
            text="Confidential financial database records for User B.",
            character_start=0,
            character_end=51,
            token_estimate=8,
            metadata_json={"document_scope": "LIBRARY"},
        )
        session.add_all([chunk_a, chunk_b])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope_a = DocumentRetrievalScope(user_id=user_a, include_library_documents=True)
        results_a = await retriever.search(
            query="financial database",
            user_id=user_a,
            top_k=5,
            retrieval_scope=scope_a,
        )

        assert len(results_a) == 1
        assert results_a[0].chunk_id == chunk_a.id
        assert results_a[0].document_id == doc_a.id


@pytest.mark.asyncio
async def test_scope_isolation_library_and_conversation(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="scope_user@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.flush()

        conv_id = uuid4()
        other_conv_id = uuid4()

        conv1 = ConversationORM(
            id=conv_id,
            user_id=user_id,
            title="Policy Conversation",
        )
        conv2 = ConversationORM(
            id=other_conv_id,
            user_id=user_id,
            title="Other Conversation",
        )
        session.add_all([conv1, conv2])
        await session.flush()

        lib_doc = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            filename="lib.txt",
            original_filename="lib.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chklib",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        conv_doc = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            conversation_id=conv_id,
            filename="conv.txt",
            original_filename="conv.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chkconv",
            status="completed",
            extractor_version="1.0",
            scope="CONVERSATION",
        )
        session.add_all([lib_doc, conv_doc])
        await session.flush()

        chunk_lib = SQLAlchemyChunk(
            id=uuid4(),
            document_id=lib_doc.id,
            chunk_index=0,
            text="Shared company policy handbook in library.",
            character_start=0,
            character_end=42,
            token_estimate=7,
            metadata_json={"document_scope": "LIBRARY"},
        )
        chunk_conv = SQLAlchemyChunk(
            id=uuid4(),
            document_id=conv_doc.id,
            chunk_index=0,
            text="Specific private note for conversation policy.",
            character_start=0,
            character_end=46,
            token_estimate=7,
            metadata_json={"document_scope": "CONVERSATION"},
        )
        session.add_all([chunk_lib, chunk_conv])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        # 1. Search with conversation scope only
        scope_conv = DocumentRetrievalScope(
            user_id=user_id,
            conversation_id=conv_id,
            include_conversation_documents=True,
            include_library_documents=False,
        )
        res_conv = await retriever.search(
            query="policy",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope_conv,
        )
        assert len(res_conv) == 1
        assert res_conv[0].chunk_id == chunk_conv.id

        # 2. Search with wrong conversation ID
        scope_wrong = DocumentRetrievalScope(
            user_id=user_id,
            conversation_id=other_conv_id,
            include_conversation_documents=True,
            include_library_documents=False,
        )
        res_wrong = await retriever.search(
            query="policy",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope_wrong,
        )
        assert res_wrong == []


@pytest.mark.asyncio
async def test_document_filtering(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="docfilt@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.flush()

        doc1 = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            filename="doc1.txt",
            original_filename="doc1.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chk11",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        doc2 = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            filename="doc2.txt",
            original_filename="doc2.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chk22",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        session.add_all([doc1, doc2])
        await session.flush()

        session.add_all([
            SQLAlchemyChunk(
                id=uuid4(),
                document_id=doc1.id,
                chunk_index=0,
                text="Architecture document on PostgreSQL scaling.",
                character_start=0,
                character_end=44,
                token_estimate=6,
                metadata_json={"document_scope": "LIBRARY"},
            ),
            SQLAlchemyChunk(
                id=uuid4(),
                document_id=doc2.id,
                chunk_index=0,
                text="Operations manual on PostgreSQL backup.",
                character_start=0,
                character_end=40,
                token_estimate=6,
                metadata_json={"document_scope": "LIBRARY"},
            ),
        ])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
        results = await retriever.search(
            query="PostgreSQL",
            user_id=user_id,
            top_k=5,
            document_ids=[doc1.id],
            retrieval_scope=scope,
        )

        assert len(results) == 1
        assert results[0].document_id == doc1.id


@pytest.mark.asyncio
async def test_deleted_document_chunks_are_not_returned(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="deluser@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.flush()

        doc = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            filename="delete_me.txt",
            original_filename="delete_me.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chkdel",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        session.add(doc)
        await session.flush()

        chunk = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=0,
            text="Ephemeral secrets that must be deleted.",
            character_start=0,
            character_end=40,
            token_estimate=6,
            metadata_json={"document_scope": "LIBRARY"},
        )
        session.add(chunk)
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)

        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)
        assert (
            len(
                await retriever.search(
                    query="Ephemeral", user_id=user_id, top_k=5, retrieval_scope=scope
                )
            )
            == 1
        )

        # Delete the document (cascade deletes chunks)
        await session.delete(doc)
        await session.commit()

        assert (
            len(
                await retriever.search(
                    query="Ephemeral", user_id=user_id, top_k=5, retrieval_scope=scope
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_special_characters_and_sql_injection_safety(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="safeuser@example.com",
                hashed_password="pwd",
                is_active=True,
            )
        )
        await session.flush()

        doc = SQLAlchemyDocument(
            id=uuid4(),
            user_id=user_id,
            filename="special.txt",
            original_filename="special.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chkspec",
            status="completed",
            extractor_version="1.0",
            scope="LIBRARY",
        )
        session.add(doc)
        await session.flush()

        session.add(
            SQLAlchemyChunk(
                id=uuid4(),
                document_id=doc.id,
                chunk_index=0,
                text="Testing special syntax: C++ / Python (3.12) & SQL queries with $100 price.",
                character_start=0,
                character_end=78,
                token_estimate=14,
                metadata_json={"document_scope": "LIBRARY"},
            )
        )
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)
        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)

        # 1. Complex punctuation
        res1 = await retriever.search(
            query="C++ / Python (3.12)",
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope,
        )
        assert len(res1) >= 1

        # 2. Malicious SQL injection attempt
        malicious_query = "'; DROP TABLE documents; -- ' OR '1'='1"
        res2 = await retriever.search(
            query=malicious_query,
            user_id=user_id,
            top_k=5,
            retrieval_scope=scope,
        )
        assert isinstance(res2, list)

        # 3. Empty and whitespace queries
        assert (
            await retriever.search(
                query="", user_id=user_id, top_k=5, retrieval_scope=scope
            )
            == []
        )
        assert (
            await retriever.search(
                query="   ", user_id=user_id, top_k=5, retrieval_scope=scope
            )
            == []
        )


@pytest.mark.asyncio
async def test_stable_ordering_for_ranking_ties(postgres_test_db):
    async with postgres_test_db() as session:
        user_id = uuid4()
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email="ties@example.com",
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
                filename="ties.txt",
                original_filename="ties.txt",
                content_type="text/plain",
                file_size=100,
                checksum="chkties",
                status="completed",
                extractor_version="1.0",
                scope="LIBRARY",
            )
        )
        await session.flush()

        # Three chunks with identical content (and thus identical ts_rank_cd)
        chunk0 = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Deterministic tie breaking test content.",
            character_start=0,
            character_end=40,
            token_estimate=5,
            metadata_json={"document_scope": "LIBRARY"},
        )
        chunk1 = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Deterministic tie breaking test content.",
            character_start=41,
            character_end=81,
            token_estimate=5,
            metadata_json={"document_scope": "LIBRARY"},
        )
        chunk2 = SQLAlchemyChunk(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=2,
            text="Deterministic tie breaking test content.",
            character_start=82,
            character_end=122,
            token_estimate=5,
            metadata_json={"document_scope": "LIBRARY"},
        )
        session.add_all([chunk0, chunk1, chunk2])
        await session.commit()

        chunk_repo = SQLAlchemyChunkRepository(session)
        retriever = PostgresSparseRetriever(db=session, chunk_repo=chunk_repo)
        scope = DocumentRetrievalScope(user_id=user_id, include_library_documents=True)

        results = await retriever.search(
            query="Deterministic tie breaking",
            user_id=user_id,
            top_k=3,
            retrieval_scope=scope,
        )

        assert len(results) == 3
        # Strict ordinal tie breaking by chunk_index
        assert results[0].chunk_index == 0
        assert results[1].chunk_index == 1
        assert results[2].chunk_index == 2
