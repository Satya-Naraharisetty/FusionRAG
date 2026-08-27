from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.services.token_estimator import CharacterTokenEstimator
from app.documents.domain.models import RetrievedChunk
from app.documents.services.context_selector import ContextSelector
from app.documents.services.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_context_selector_parent_child_deduplication():
    """
    Verifies that when multiple child chunks from the same parent chunk match,
    ContextSelector deduplicates them into a single parent context without repeating.
    """
    estimator = CharacterTokenEstimator()
    selector = ContextSelector(
        token_estimator=estimator,
        max_context_tokens=1000,
        enable_parent_child=True,
    )

    doc_id = uuid4()
    parent_id = str(uuid4())
    parent_text = "This is the complete parent paragraph containing rich architectural explanations."

    child1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="spec.pdf",
        text="child chunk 1",
        similarity_score=0.92,
        normalized_score=0.92,
        metadata={
            "parent_chunk_id": parent_id,
            "parent_text": parent_text,
            "chunk_type": "child",
        },
        chunk_index=0,
    )
    child2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="spec.pdf",
        text="child chunk 2",
        similarity_score=0.88,
        normalized_score=0.88,
        metadata={
            "parent_chunk_id": parent_id,
            "parent_text": parent_text,
            "chunk_type": "child",
        },
        chunk_index=1,
    )

    result = await selector.select_context([child1, child2])

    # Exactly 1 parent chunk should be selected in final context
    assert len(result.selected_chunks) == 1
    assert result.selected_chunks[0].chunk_id == child1.chunk_id
    assert parent_text in result.concatenated_context
    assert "[Chunk 1]" in result.concatenated_context
    assert "[Chunk 2]" not in result.concatenated_context


@pytest.mark.asyncio
async def test_context_selector_sentence_window_expansion():
    """
    Verifies that when sentence-window chunks match, ContextSelector expands the formatted
    context to the surrounding window text while preserving target chunk identity.
    """
    estimator = CharacterTokenEstimator()
    selector = ContextSelector(
        token_estimator=estimator,
        max_context_tokens=1000,
        enable_sentence_window=True,
    )

    doc_id = uuid4()
    sent_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="policy.txt",
        text="Target sentence matched.",
        similarity_score=0.95,
        normalized_score=0.95,
        metadata={
            "chunk_type": "sentence_window",
            "sentence_index": 2,
            "window_text": "Preceding context sentence. Target sentence matched. Subsequent context sentence.",
        },
        chunk_index=2,
    )

    result = await selector.select_context([sent_chunk])

    assert len(result.selected_chunks) == 1
    assert "Preceding context sentence." in result.concatenated_context
    assert "Target sentence matched." in result.concatenated_context
    assert "Subsequent context sentence." in result.concatenated_context


@pytest.mark.asyncio
async def test_context_selector_legacy_chunks_fallback():
    """
    Verifies backwards compatibility: legacy chunks without parent/window metadata
    are formatted using standard text without crashing.
    """
    estimator = CharacterTokenEstimator()
    selector = ContextSelector(
        token_estimator=estimator,
        max_context_tokens=1000,
        enable_parent_child=True,
        enable_sentence_window=True,
    )

    doc_id = uuid4()
    legacy_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="legacy.txt",
        text="Standard legacy text without extra metadata.",
        similarity_score=0.85,
        normalized_score=0.85,
        metadata={},
        chunk_index=0,
    )

    result = await selector.select_context([legacy_chunk])

    assert len(result.selected_chunks) == 1
    assert "Standard legacy text without extra metadata." in result.concatenated_context


@pytest.mark.asyncio
async def test_embedding_service_uses_contextual_text():
    """
    Verifies that EmbeddingService computes embeddings over metadata['contextual_text']
    when present, while maintaining original chunk text in database/provenance.
    """
    from datetime import UTC, datetime

    from app.documents.domain.models import Chunk

    doc_id = uuid4()
    chunk_id = uuid4()
    raw_text = "Dense vector search enables semantic discovery."
    contextual_text = (
        "[Document: whitepaper.pdf]\nDense vector search enables semantic discovery."
    )

    chunk = Chunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=0,
        text=raw_text,
        character_start=0,
        character_end=len(raw_text),
        token_estimate=10,
        metadata={"contextual_text": contextual_text},
        created_at=datetime.now(UTC),
    )

    mock_doc_repo = AsyncMock()
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.user_id = uuid4()
    mock_doc.scope = "LIBRARY"
    mock_doc.conversation_id = None
    mock_doc.language = "en"
    mock_doc_repo.get_by_id.return_value = mock_doc

    mock_chunk_repo = AsyncMock()
    mock_chunk_repo.list_by_document.return_value = [chunk]

    mock_embedding_repo = AsyncMock()
    mock_embedding_repo.list_by_chunk_ids.return_value = []

    mock_generator = AsyncMock()
    mock_generator.batch_generate.return_value = [[0.1] * 768]

    mock_vector_store = AsyncMock()
    mock_uow = AsyncMock()
    mock_time = MagicMock()
    mock_time.get_now.return_value = datetime.now(UTC)

    mock_uuid = MagicMock()
    mock_uuid.generate.return_value = uuid4()

    service = EmbeddingService(
        document_repo=mock_doc_repo,
        chunk_repo=mock_chunk_repo,
        embedding_repo=mock_embedding_repo,
        embedding_generator=mock_generator,
        vector_store=mock_vector_store,
        uuid_generator=mock_uuid,
        provider_name="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding_version="v1",
        uow=mock_uow,
        time_provider=mock_time,
        batch_size=16,
    )

    await service.generate_embeddings(doc_id)

    # Verification: Generator was called with contextual_text
    mock_generator.batch_generate.assert_called_once_with([contextual_text])
    # Verification: VectorStore was called with payload retaining chunk.metadata
    mock_vector_store.upsert.assert_called_once()
