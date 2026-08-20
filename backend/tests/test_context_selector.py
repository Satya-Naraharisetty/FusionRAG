import datetime
import uuid
from unittest.mock import AsyncMock

import pytest

from app.chat.services.token_estimator import CharacterTokenEstimator
from app.documents.domain.models import Chunk, RetrievedChunk
from app.documents.services.context_selector import ContextSelector, SelectedContext


@pytest.fixture
def token_estimator():
    return CharacterTokenEstimator()


def _create_chunk(
    doc_name: str,
    doc_id: uuid.UUID,
    chunk_idx: int,
    text: str,
    rerank_score: float | None = None,
    sim_score: float = 0.8,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_name=doc_name,
        text=text,
        similarity_score=sim_score,
        normalized_score=sim_score,
        rerank_score=rerank_score,
        metadata={"section": f"Section {chunk_idx}"},
        chunk_index=chunk_idx,
    )


@pytest.mark.asyncio
async def test_context_selector_enforces_token_budget(token_estimator):
    doc_id = uuid.uuid4()
    chunks = [
        _create_chunk(
            "doc.md",
            doc_id,
            i,
            f"Long paragraph text content {i} " * 50,
            rerank_score=0.9 - i * 0.1,
        )
        for i in range(10)
    ]

    selector = ContextSelector(
        token_estimator=token_estimator,
        max_context_tokens=100,  # Strict token budget
        max_chunks=10,
    )

    selected: SelectedContext = await selector.select_context(chunks)
    assert selected.truncated
    assert selected.token_count <= 100
    assert len(selected.selected_chunks) < 10


@pytest.mark.asyncio
async def test_context_selector_score_threshold_by_source(token_estimator):
    doc_id = uuid.uuid4()
    c1 = _create_chunk("doc1.md", doc_id, 0, "High relevance chunk", rerank_score=0.95)
    c2 = _create_chunk("doc2.md", doc_id, 1, "Low relevance chunk", rerank_score=0.10)

    selector = ContextSelector(
        token_estimator=token_estimator,
        max_context_tokens=4000,
        min_chunk_score=0.50,
        score_source="rerank_score",
    )

    selected = await selector.select_context([c1, c2])
    assert len(selected.selected_chunks) == 1
    assert selected.selected_chunks[0].chunk_id == c1.chunk_id


@pytest.mark.asyncio
async def test_context_selector_removes_duplicates(token_estimator):
    doc_id = uuid.uuid4()
    c1 = _create_chunk("doc1.md", doc_id, 0, "Unique chunk text", rerank_score=0.9)
    # Duplicate chunk instance
    c1_dup = _create_chunk("doc1.md", doc_id, 0, "Unique chunk text", rerank_score=0.9)
    object.__setattr__(c1_dup, "chunk_id", c1.chunk_id)

    selector = ContextSelector(token_estimator=token_estimator, max_context_tokens=4000)
    selected = await selector.select_context([c1, c1_dup])
    assert len(selected.selected_chunks) == 1


@pytest.mark.asyncio
async def test_context_selector_ordering_prioritizes_rerank_score(token_estimator):
    doc_id = uuid.uuid4()
    c1 = _create_chunk("doc1.md", doc_id, 0, "Chunk 1", rerank_score=0.40)
    c2 = _create_chunk("doc2.md", doc_id, 1, "Chunk 2", rerank_score=0.99)
    c3 = _create_chunk("doc3.md", doc_id, 2, "Chunk 3", rerank_score=0.75)

    selector = ContextSelector(token_estimator=token_estimator, max_context_tokens=4000)
    selected = await selector.select_context([c1, c2, c3])
    assert [c.chunk_id for c in selected.selected_chunks] == [
        c2.chunk_id,
        c3.chunk_id,
        c1.chunk_id,
    ]


@pytest.mark.asyncio
async def test_neighbor_chunks_same_document_only(token_estimator):
    doc_id = uuid.uuid4()
    foreign_doc_id = uuid.uuid4()

    mock_repo = AsyncMock()
    # Mock DB chunks for doc_id
    neighbor_db_chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_index=1,
        text="Adjacent section neighbor chunk text",
        character_start=100,
        character_end=200,
        token_estimate=20,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    mock_repo.list_by_document.return_value = [neighbor_db_chunk]
    mock_repo.get_chunks_by_document.return_value = [neighbor_db_chunk]

    primary_chunk = _create_chunk(
        "doc.md", doc_id, 0, "Primary chunk", rerank_score=0.9
    )

    selector = ContextSelector(
        token_estimator=token_estimator,
        enable_neighbor_chunks=True,
        neighbor_window=1,
        chunk_repo=mock_repo,
        max_context_tokens=4000,
    )

    selected = await selector.select_context([primary_chunk], allowed_doc_ids={doc_id})

    assert selected.neighbor_chunks_added >= 1
    chunk_doc_ids = {c.document_id for c in selected.selected_chunks}
    assert chunk_doc_ids == {doc_id}
    assert foreign_doc_id not in chunk_doc_ids


@pytest.mark.asyncio
async def test_neighbor_chunks_blocked_if_outside_allowed_scope(token_estimator):
    doc_id = uuid.uuid4()
    mock_repo = AsyncMock()

    primary_chunk = _create_chunk(
        "unauthorized_doc.md", doc_id, 0, "Primary chunk", rerank_score=0.9
    )

    selector = ContextSelector(
        token_estimator=token_estimator,
        enable_neighbor_chunks=True,
        neighbor_window=1,
        chunk_repo=mock_repo,
        max_context_tokens=4000,
    )

    # Allowed doc IDs does NOT include doc_id
    selected = await selector.select_context(
        [primary_chunk], allowed_doc_ids={uuid.uuid4()}
    )
    assert selected.neighbor_chunks_added == 0
