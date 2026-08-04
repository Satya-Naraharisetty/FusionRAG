import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import (
    get_current_user_context,
    get_retrieval_service,
    get_conversation_manager,
)
from app.auth.infrastructure.persistence.models import Base, SQLAlchemyUser
from app.core.config import settings
from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.models import Chunk, RetrievedChunk, SearchResult
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.services.ranking import SemanticSearchRanker
from app.documents.services.retrieval_service import RetrievalService

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"


# --- DB Mock/Fixtures for Repository Integration Tests ---
@pytest.fixture(scope="function")
def search_test_db():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    try:
        db.execute(
            Base.metadata.tables["document_chunks"].delete()
        )  # clean chunks
        db.execute(Base.metadata.tables["documents"].delete())  # clean docs
        db.execute(Base.metadata.tables["users"].delete())  # clean users
        db.commit()
    finally:
        db.close()
    return session_factory


# --- 1. SearchRanker Unit Tests ---
def test_semantic_search_ranker():
    ranker = SemanticSearchRanker()
    doc_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="text 1",
            similarity_score=0.45,
            normalized_score=0.725,
            metadata={},
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="text 2",
            similarity_score=0.88,
            normalized_score=0.94,
            metadata={},
            chunk_index=1,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="text 3",
            similarity_score=0.62,
            normalized_score=0.81,
            metadata={},
            chunk_index=2,
        ),
    ]

    ranked = ranker.rank("query", chunks)
    assert len(ranked) == 3
    assert ranked[0].similarity_score == 0.88
    assert ranked[1].similarity_score == 0.62
    assert ranked[2].similarity_score == 0.45


# --- 2. ChunkRepository Integration Tests ---
@pytest.mark.asyncio
async def test_chunk_repository_operations(search_test_db):
    db = search_test_db()
    try:
        repo = SQLAlchemyChunkRepository(db)

        # 1. Setup mock user and document in DB
        u_id = uuid4()
        db_user = SQLAlchemyUser(
            id=u_id,
            email=f"{u_id}@test.com",
            hashed_password="hash",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(db_user)
        db.flush()

        doc_id = uuid4()
        db_doc = SQLAlchemyDocument(
            id=doc_id,
            user_id=u_id,
            filename="legal_document.txt",
            original_filename="legal_document.txt",
            content_type="text/plain",
            file_size=1000,
            checksum="hash1",
            status="completed",
        )
        db.add(db_doc)
        db.flush()

        chunk_id = uuid4()
        db_chunk = SQLAlchemyChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            text="Lorem Ipsum text content here.",
            character_start=0,
            character_end=30,
            token_estimate=6,
            metadata_json={"source": "law"},
        )
        db.add(db_chunk)
        db.commit()

        # 2. Test load_chunk_text
        text = await repo.load_chunk_text(chunk_id)
        assert text == "Lorem Ipsum text content here."

        missing_text = await repo.load_chunk_text(uuid4())
        assert missing_text is None

        # 3. Test load_metadata
        meta = await repo.load_metadata(chunk_id)
        assert meta == {"source": "law"}

        # 4. Test verify_document_ownership
        ownership_valid = await repo.verify_document_ownership([doc_id], u_id)
        assert ownership_valid is True

        ownership_invalid_user = await repo.verify_document_ownership(
            [doc_id], uuid4()
        )
        assert ownership_invalid_user is False

        ownership_invalid_doc = await repo.verify_document_ownership(
            [uuid4()], u_id
        )
        assert ownership_invalid_doc is False

        # Empty ownership verification list should return True
        ownership_empty = await repo.verify_document_ownership([], u_id)
        assert ownership_empty is True

        # Duplicate doc ids list verification
        ownership_duplicates = await repo.verify_document_ownership(
            [doc_id, doc_id], u_id
        )
        assert ownership_duplicates is True

        # 5. Test batch_lookup
        chunks = await repo.batch_lookup([chunk_id])
        assert len(chunks) == 1
        assert chunks[0].text == "Lorem Ipsum text content here."
        # Verify that original_filename is eagerly loaded into metadata["document_name"]
        assert chunks[0].metadata["document_name"] == "legal_document.txt"

    finally:
        db.close()


# --- 3. RetrievalService Unit Tests ---
@pytest.mark.asyncio
async def test_retrieval_service_success(mocker):
    # Mock Collaborators
    gen = mocker.MagicMock()
    gen.generate.return_value = [0.1, 0.2, 0.3]

    store = mocker.MagicMock()
    store.search = mocker.AsyncMock(
        return_value=[
            {"id": UUID("11111111-1111-1111-1111-111111111111"), "score": 0.8},
            {"id": UUID("22222222-2222-2222-2222-222222222222"), "score": 0.6},
        ]
    )

    repo = mocker.MagicMock()
    repo.verify_document_ownership = mocker.AsyncMock(return_value=True)

    c1 = Chunk(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        document_id=uuid4(),
        chunk_index=0,
        text="text 1",
        character_start=0,
        character_end=5,
        token_estimate=1,
        created_at=datetime.now(UTC),
    )
    c1.metadata["document_name"] = "document_1.txt"

    c2 = Chunk(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        document_id=uuid4(),
        chunk_index=1,
        text="text 2",
        character_start=5,
        character_end=10,
        token_estimate=1,
        created_at=datetime.now(UTC),
    )
    c2.metadata["document_name"] = "document_2.txt"

    repo.batch_lookup = mocker.AsyncMock(return_value=[c1, c2])

    ranker = mocker.MagicMock()
    ranker.rank.side_effect = lambda q, chunks: chunks

    service = RetrievalService(
        embedding_generator=gen,
        vector_store=store,
        chunk_repo=repo,
        ranker=ranker,
        similarity_threshold=0.25,
        search_timeout=3.0,
    )

    result = await service.retrieve(
        query="test query", user_id=uuid4(), top_k=10
    )

    assert result.original_query == "test query"
    assert result.total_matches == 2
    assert result.search_strategy == "semantic"
    assert len(result.retrieved_chunks) == 2
    assert result.retrieved_chunks[0].similarity_score == 0.8
    assert (
        result.retrieved_chunks[0].normalized_score == 0.9
    )  # (0.8 + 1) / 2 = 0.9
    assert result.retrieved_chunks[0].document_name == "document_1.txt"


@pytest.mark.asyncio
async def test_retrieval_service_ownership_violation(mocker):
    gen = mocker.MagicMock()
    store = mocker.MagicMock()
    repo = mocker.MagicMock()
    repo.verify_document_ownership = mocker.AsyncMock(
        return_value=False
    )  # Violation!
    ranker = mocker.MagicMock()

    service = RetrievalService(
        embedding_generator=gen,
        vector_store=store,
        chunk_repo=repo,
        ranker=ranker,
    )

    with pytest.raises(UnauthorizedDocumentAccess):
        await service.retrieve(
            query="test",
            user_id=uuid4(),
            top_k=10,
            document_ids=[uuid4(), uuid4()],
        )


@pytest.mark.asyncio
async def test_retrieval_service_similarity_threshold(mocker):
    gen = mocker.MagicMock()
    gen.generate.return_value = [0.1]

    store = mocker.MagicMock()
    # Mocking two scores: one above threshold (0.8), one below (0.1)
    store.search = mocker.AsyncMock(
        return_value=[
            {"id": UUID("11111111-1111-1111-1111-111111111111"), "score": 0.8},
            {"id": UUID("22222222-2222-2222-2222-222222222222"), "score": 0.1},
        ]
    )

    repo = mocker.MagicMock()
    c1 = Chunk(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        document_id=uuid4(),
        chunk_index=0,
        text="text 1",
        character_start=0,
        character_end=5,
        token_estimate=1,
        created_at=datetime.now(UTC),
    )
    c2 = Chunk(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        document_id=uuid4(),
        chunk_index=1,
        text="text 2",
        character_start=5,
        character_end=10,
        token_estimate=1,
        created_at=datetime.now(UTC),
    )
    repo.batch_lookup = mocker.AsyncMock(return_value=[c1, c2])

    ranker = mocker.MagicMock()
    ranker.rank.side_effect = lambda q, chunks: chunks

    # Set SIMILARITY_THRESHOLD = 0.5
    service = RetrievalService(
        embedding_generator=gen,
        vector_store=store,
        chunk_repo=repo,
        ranker=ranker,
        similarity_threshold=0.5,
    )

    result = await service.retrieve(query="test", user_id=uuid4(), top_k=10)

    # c2 (score 0.1) should be filtered out
    assert len(result.retrieved_chunks) == 1
    assert result.retrieved_chunks[0].chunk_id == c1.id


@pytest.mark.asyncio
async def test_retrieval_service_empty_results(mocker):
    gen = mocker.MagicMock()
    gen.generate.return_value = [0.1]
    store = mocker.MagicMock()
    store.search = mocker.AsyncMock(return_value=[])  # No matches
    repo = mocker.MagicMock()
    ranker = mocker.MagicMock()

    service = RetrievalService(
        embedding_generator=gen,
        vector_store=store,
        chunk_repo=repo,
        ranker=ranker,
    )

    result = await service.retrieve(query="test", user_id=uuid4(), top_k=10)

    assert result.total_matches == 0
    assert len(result.retrieved_chunks) == 0
    # verify DB wasn't queried if no vector matches
    assert repo.batch_lookup.call_count == 0


# --- 4. API /search Endpoint Integration Tests ---
def test_api_search_validation_and_capping(client, mocker):
    user_id = uuid4()
    client.app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id),
        "role": "user",
    }

    # Mock ConversationManager
    from app.chat.domain.models import Conversation, ConversationState, HistoryRewriteResult
    from app.chat.services.conversation_manager import ConversationManager

    mock_conv = Conversation(
        id=uuid4(),
        user_id=user_id,
        title="Mock",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    mock_conv_manager = mocker.MagicMock()
    mock_conv_manager.get_or_create_conversation = mocker.AsyncMock(return_value=mock_conv)
    mock_conv_manager._memory.load_memory = mocker.AsyncMock(return_value=([], None))
    mock_conv_manager._rewriter.rewrite = mocker.AsyncMock(
        return_value=HistoryRewriteResult(
            original_query="test query",
            rewritten_query="test query",
            rewrite_reason="No history",
            rewrite_applied=False,
        )
    )
    client.app.dependency_overrides[get_conversation_manager] = lambda: mock_conv_manager

    # Mock the RetrievalService dependency
    mock_retrieval_service = mocker.MagicMock()
    mock_retrieval_service.retrieve = mocker.AsyncMock(
        return_value=SearchResult(
            original_query="query text",
            retrieval_time=0.015,
            total_matches=0,
            retrieved_chunks=[],
        )
    )

    client.app.dependency_overrides[get_retrieval_service] = (
        lambda: mock_retrieval_service
    )

    # Scenario A: Test top_k <= 0 returns validation error (422)
    response = client.post(
        "/api/v1/search",
        json={"query": "test query", "top_k": 0},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Scenario B: Test top_k is capped at MAX_TOP_K
    resp = client.post(
        "/api/v1/search",
        json={"query": "test query", "top_k": 500},
    )
    print("SCENARIO B RESPONSE:", resp.status_code, resp.text)
    _, kwargs = mock_retrieval_service.retrieve.call_args
    assert kwargs["top_k"] == settings.MAX_TOP_K

    # Scenario C: Clean up dependency overrides
    client.app.dependency_overrides.clear()


def test_api_search_unauthorized_document(client, mocker):
    user_id = uuid4()
    client.app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id),
        "role": "user",
    }

    # Mock ConversationManager
    from app.chat.domain.models import Conversation, ConversationState, HistoryRewriteResult
    mock_conv = Conversation(
        id=uuid4(),
        user_id=user_id,
        title="Mock",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    mock_conv_manager = mocker.MagicMock()
    mock_conv_manager.get_or_create_conversation = mocker.AsyncMock(return_value=mock_conv)
    mock_conv_manager._memory.load_memory = mocker.AsyncMock(return_value=([], None))
    mock_conv_manager._rewriter.rewrite = mocker.AsyncMock(
        return_value=HistoryRewriteResult(
            original_query="test",
            rewritten_query="test",
            rewrite_reason="No history",
            rewrite_applied=False,
        )
    )
    client.app.dependency_overrides[get_conversation_manager] = lambda: mock_conv_manager

    # Mock retrieval service to raise UnauthorizedDocumentAccess
    mock_retrieval_service = mocker.MagicMock()
    mock_retrieval_service.retrieve = mocker.AsyncMock(
        side_effect=UnauthorizedDocumentAccess("Unauthorized access")
    )

    client.app.dependency_overrides[get_retrieval_service] = (
        lambda: mock_retrieval_service
    )

    response = client.post(
        "/api/v1/search",
        json={"query": "test", "document_ids": [str(uuid4())]},
    )
    # The global handler or the endpoint translates this to 403 Forbidden
    assert response.status_code == status.HTTP_403_FORBIDDEN

    client.app.dependency_overrides.clear()
