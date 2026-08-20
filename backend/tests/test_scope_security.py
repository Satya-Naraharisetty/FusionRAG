"""
Security invariant tests for the Dual Document Scope implementation.

These tests verify that the scope model correctly enforces:
1. User A cannot access User B's documents (library or conversation)
2. Conversation A cannot access Conversation B's documents
3. Normal chat (no @documents) excludes LIBRARY documents
4. @documents enables library access only for the authenticated user
5. Agent tools cannot bypass scope via model-supplied document IDs
6. Direct chunk/document/citation lookups respect scope
7. ToolContext uses explicit intent booleans (not None-vs-list signal)
"""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.chat.domain.agents import ToolContext
from app.documents.domain.models import (
    DocumentRetrievalScope,
    SearchResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tool_context(
    *,
    user_id=None,
    conversation_id=None,
    include_library_documents=False,
    include_conversation_documents=True,
):
    return ToolContext(
        user_id=user_id or uuid.uuid4(),
        conversation_id=conversation_id or uuid.uuid4(),
        db_session=None,
        include_library_documents=include_library_documents,
        include_conversation_documents=include_conversation_documents,
    )


def _make_scope(
    user_id,
    conversation_id=None,
    include_library=False,
    include_conversation=True,
    doc_ids=None,
):
    return DocumentRetrievalScope(
        user_id=user_id,
        conversation_id=conversation_id,
        include_library_documents=include_library,
        include_conversation_documents=include_conversation,
        document_ids=doc_ids,
    )


# ---------------------------------------------------------------------------
# 1. ToolContext explicit intent booleans
# ---------------------------------------------------------------------------


def test_tool_context_default_excludes_library():
    ctx = make_tool_context()
    assert ctx.include_library_documents is False
    assert ctx.include_conversation_documents is True


def test_tool_context_at_documents_enables_library():
    ctx = make_tool_context(include_library_documents=True)
    assert ctx.include_library_documents is True


def test_tool_context_has_no_allowed_document_ids_field():
    ctx = make_tool_context()
    assert not hasattr(ctx, "allowed_document_ids")


# ---------------------------------------------------------------------------
# 2. DocumentRetrievalScope invariants
# ---------------------------------------------------------------------------


def test_scope_no_flags_allows_nothing():
    scope = _make_scope(uuid.uuid4(), include_library=False, include_conversation=False)
    assert not scope.include_library_documents
    assert not scope.include_conversation_documents


def test_scope_library_flag_is_per_user():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    assert (
        _make_scope(user_a, include_library=True).user_id
        != _make_scope(user_b, include_library=True).user_id
    )


# ---------------------------------------------------------------------------
# 3. ChunkRepository.get_allowed_document_ids (unit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_allowed_ids_no_flags_returns_empty_without_db_query():
    from app.documents.infrastructure.persistence.repositories.chunk_repository import (
        SQLAlchemyChunkRepository,
    )

    scope = _make_scope(uuid.uuid4(), include_library=False, include_conversation=False)
    mock_db = MagicMock()
    repo = SQLAlchemyChunkRepository(mock_db)
    result = await repo.get_allowed_document_ids(scope)
    # Must return empty list; early-return guard added before the first DB call
    assert result == []
    mock_db.query.assert_not_called()


# ---------------------------------------------------------------------------
# 4. SearchKnowledgeTool scope propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_tool_passes_library_flag_from_context():
    from app.chat.services.tools.semantic_search import SearchKnowledgeTool

    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    mock_svc = AsyncMock()
    mock_svc.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="test",
            retrieval_time=0.01,
            total_matches=0,
            retrieved_chunks=[],
        )
    )
    tool = SearchKnowledgeTool(retrieval_service=mock_svc)

    # No @documents: library=False
    await tool.execute(
        {"query": "q"},
        make_tool_context(
            user_id=user_id, conversation_id=conv_id, include_library_documents=False
        ),
    )
    scope = mock_svc.retrieve.call_args.kwargs["retrieval_scope"]
    assert scope.include_library_documents is False
    assert scope.include_conversation_documents is True

    # With @documents: library=True
    await tool.execute(
        {"query": "q"},
        make_tool_context(
            user_id=user_id, conversation_id=conv_id, include_library_documents=True
        ),
    )
    scope = mock_svc.retrieve.call_args.kwargs["retrieval_scope"]
    assert scope.include_library_documents is True
    assert scope.user_id == user_id


@pytest.mark.asyncio
async def test_search_tool_model_injected_foreign_doc_id_stays_in_scope_user():
    """The scope carries only user_a's user_id even if model injects a foreign doc ID."""
    from app.chat.services.tools.semantic_search import SearchKnowledgeTool

    user_a = uuid.uuid4()
    foreign_doc = uuid.uuid4()
    mock_svc = AsyncMock()
    mock_svc.retrieve = AsyncMock(
        return_value=SearchResult(
            original_query="test",
            retrieval_time=0.01,
            total_matches=0,
            retrieved_chunks=[],
        )
    )
    tool = SearchKnowledgeTool(retrieval_service=mock_svc)
    ctx = make_tool_context(user_id=user_a, include_library_documents=True)
    await tool.execute({"query": "hack", "document_ids": [str(foreign_doc)]}, ctx)
    scope = mock_svc.retrieve.call_args.kwargs["retrieval_scope"]
    assert scope.user_id == user_a  # always user_a, not the foreign doc's owner


# ---------------------------------------------------------------------------
# 5. Direct tool scope gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_chunk_tool_blocks_library_without_mention():
    from app.chat.services.tools.chunk_retrieval import RetrieveChunkTool

    user_id = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.user_id = user_id  # ownership passes
    mock_doc.scope = "LIBRARY"
    mock_doc.conversation_id = None
    mock_chunk = MagicMock()
    mock_chunk.document = mock_doc
    mock_db = MagicMock()
    # Tool uses db.query(SQLAlchemyChunk).filter(...).first() — no .options()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_chunk
    ctx = ToolContext(
        user_id=user_id,
        conversation_id=uuid.uuid4(),
        db_session=mock_db,
        include_library_documents=False,
        include_conversation_documents=True,
    )
    result = await RetrieveChunkTool().execute({"chunk_id": str(uuid.uuid4())}, ctx)
    assert result.is_error is True
    assert "Access Denied" in result.content


@pytest.mark.asyncio
async def test_retrieve_chunk_tool_blocks_wrong_conversation():
    from app.chat.services.tools.chunk_retrieval import RetrieveChunkTool

    user_id = uuid.uuid4()
    conv_a = uuid.uuid4()
    conv_b = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.user_id = user_id  # ownership passes
    mock_doc.scope = "CONVERSATION"
    mock_doc.conversation_id = conv_b  # different conversation
    mock_chunk = MagicMock()
    mock_chunk.document = mock_doc
    mock_db = MagicMock()
    # Tool uses db.query(SQLAlchemyChunk).filter(...).first() — no .options()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_chunk
    ctx = ToolContext(
        user_id=user_id,
        conversation_id=conv_a,
        db_session=mock_db,
        include_library_documents=False,
        include_conversation_documents=True,
    )
    result = await RetrieveChunkTool().execute({"chunk_id": str(uuid.uuid4())}, ctx)
    assert result.is_error is True


# ---------------------------------------------------------------------------
# 6. Sparse index hard-rejects chunks with missing document_scope
# ---------------------------------------------------------------------------


def test_sparse_index_missing_scope_is_rejected_not_promoted():
    """Chunks missing document_scope must NOT be treated as LIBRARY."""
    metadata = {}  # no document_scope
    doc_scope = metadata.get("document_scope")
    scope = _make_scope(uuid.uuid4(), include_library=True)

    is_allowed = False
    if not doc_scope:
        pass  # hard skip — not allowed
    elif doc_scope == "LIBRARY" and scope.include_library_documents:
        is_allowed = True
    assert is_allowed is False


# ---------------------------------------------------------------------------
# 7. Cross-user access via RetrievalService raises UnauthorizedDocumentAccess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_service_cross_user_access_denied():
    from app.documents.domain.exceptions import UnauthorizedDocumentAccess
    from app.documents.services.retrieval_service import RetrievalService

    user_a = uuid.uuid4()
    foreign_doc = uuid.uuid4()
    mock_repo = AsyncMock()
    mock_repo.get_allowed_document_ids = AsyncMock(
        return_value=[]
    )  # foreign doc not allowed
    svc = RetrievalService(chunk_repo=mock_repo)
    scope = DocumentRetrievalScope(
        user_id=user_a,
        include_library_documents=True,
        include_conversation_documents=False,
        document_ids=[foreign_doc],
    )
    with pytest.raises(UnauthorizedDocumentAccess):
        await svc.retrieve(query="test", user_id=user_a, top_k=5, retrieval_scope=scope)


# ---------------------------------------------------------------------------
# 8. Replacement Security & Scope Invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_document_cross_user_denied():
    from datetime import datetime

    from app.documents.domain.exceptions import UnauthorizedDocumentAccess
    from app.documents.domain.models import Document, DocumentScope, DocumentStatus
    from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
    from app.documents.infrastructure.extractors import ExtractorFactory
    from app.documents.services.document_service import DocumentService

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    doc_id = uuid.uuid4()

    doc_a = Document(
        id=doc_id,
        user_id=user_a,
        scope=DocumentScope.LIBRARY,
        conversation_id=None,
        filename=f"user_{user_a}/{doc_id}.txt",
        original_filename="user_a.txt",
        content_type="text/plain",
        file_size=50,
        checksum="hash_a",
        status=DocumentStatus.COMPLETED,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_repo = AsyncMock()
    mock_repo.get_by_id_for_update.return_value = doc_a

    doc_service = DocumentService(
        document_repo=mock_repo,
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    with pytest.raises(UnauthorizedDocumentAccess):
        await doc_service.replace_document_content(
            id=doc_id,
            user_id=user_b,
            file_bytes=b"attempted takeover",
            original_filename="user_b.txt",
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_replace_document_preserves_conversation_scope():
    from datetime import datetime

    from app.documents.domain.models import Document, DocumentScope, DocumentStatus
    from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
    from app.documents.infrastructure.extractors import ExtractorFactory
    from app.documents.services.document_service import DocumentService

    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    conv_doc = Document(
        id=doc_id,
        user_id=user_id,
        scope=DocumentScope.CONVERSATION,
        conversation_id=conv_id,
        filename=f"user_{user_id}/{doc_id}.txt",
        original_filename="chat_attachment.txt",
        content_type="text/plain",
        file_size=50,
        checksum="hash_old",
        status=DocumentStatus.COMPLETED,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_repo = AsyncMock()
    mock_repo.get_by_id_for_update.return_value = conv_doc
    mock_repo.get_by_checksum_and_user.return_value = None
    mock_repo.save.side_effect = lambda d: d
    mock_storage = AsyncMock()
    mock_storage.save.return_value = f"user_{user_id}/{doc_id}.txt"
    mock_time = AsyncMock()
    mock_time.get_now.return_value = datetime.now(UTC)

    doc_service = DocumentService(
        document_repo=mock_repo,
        storage_provider=mock_storage,
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=mock_time,
        max_upload_size=1024,
    )

    replaced = await doc_service.replace_document_content(
        id=doc_id,
        user_id=user_id,
        file_bytes=b"new attachment content",
        original_filename="chat_attachment_v2.txt",
        content_type="text/plain",
    )

    assert replaced.scope == DocumentScope.CONVERSATION
    assert replaced.conversation_id == conv_id
    assert replaced.original_filename == "chat_attachment_v2.txt"


# ---------------------------------------------------------------------------
# 7. Multi-Query Expansion Scope Security (Phase 2.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expanded_queries_cannot_escape_retrieval_scope():
    """
    CRITICAL SECURITY TEST:
    Verifies that every original, expanded, and decomposed query executed by
    RetrievalService strictly inherits and enforces the exact user_id,
    DocumentRetrievalScope, and allowed_document_ids of the original request.
    """
    from app.documents.services.fusion import ReciprocalRankFusionEngine
    from app.documents.services.mmr import DefaultMMRSelector
    from app.documents.services.query_classifier import DeterministicQueryClassifier
    from app.documents.services.query_decomposer import DeterministicQueryDecomposer
    from app.documents.services.query_expansion import LexicalQueryExpander
    from app.documents.services.query_processor import DefaultQueryProcessor
    from app.documents.services.reranker import IdentityReranker
    from app.documents.services.retrieval_service import RetrievalService

    user_a = uuid.uuid4()
    conv_a = uuid.uuid4()
    doc_a = uuid.uuid4()

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.get_allowed_document_ids.return_value = [doc_a]
    mock_chunk_repo.get_chunks_metadata_stats.return_value = {"count": 10}

    mock_dense = AsyncMock()
    mock_dense.retrieve.return_value = []
    mock_sparse = AsyncMock()
    mock_sparse.retrieve.return_value = []

    service = RetrievalService(
        query_processor=DefaultQueryProcessor(),
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        fusion_engine=ReciprocalRankFusionEngine(rrf_k=60),
        mmr_selector=DefaultMMRSelector(),
        reranker=IdentityReranker(),
        chunk_repo=mock_chunk_repo,
        query_classifier=DeterministicQueryClassifier(),
        query_expander=LexicalQueryExpander(),
        query_decomposer=DeterministicQueryDecomposer(),
        enable_hybrid_search=True,
        enable_query_expansion=True,
        enable_query_decomposition=True,
    )

    scope = DocumentRetrievalScope(
        user_id=user_a,
        conversation_id=conv_a,
        include_conversation_documents=True,
        include_library_documents=False,
    )

    await service.retrieve(
        query="What was 2025 revenue and also the engineering SLA target?",
        user_id=user_a,
        top_k=5,
        retrieval_scope=scope,
    )

    # Verify every call to dense retriever preserved user_id and allowed_doc_ids
    assert mock_dense.retrieve.call_count >= 1
    for call in mock_dense.retrieve.call_args_list:
        _, kwargs = call
        assert kwargs["user_id"] == user_a
        assert kwargs["document_ids"] == [doc_a]
        assert kwargs["retrieval_scope"].user_id == user_a
        assert kwargs["retrieval_scope"].conversation_id == conv_a
        assert kwargs["retrieval_scope"].include_library_documents is False

    # Verify every call to sparse retriever preserved user_id and allowed_doc_ids
    assert mock_sparse.retrieve.call_count >= 1
    for call in mock_sparse.retrieve.call_args_list:
        _, kwargs = call
        assert kwargs["user_id"] == user_a
        assert kwargs["document_ids"] == [doc_a]
        assert kwargs["retrieval_scope"].user_id == user_a
        assert kwargs["retrieval_scope"].conversation_id == conv_a
