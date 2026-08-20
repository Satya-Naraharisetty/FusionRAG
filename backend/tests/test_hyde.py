import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.documents.domain.interfaces import DenseRetriever, EmbeddingGenerator
from app.documents.domain.models import RetrievedChunk
from app.documents.services.hyde import (
    DeterministicHyDEGenerator,
    HypotheticalDocument,
    SafeHyDEExecutor,
)


@pytest.mark.asyncio
async def test_deterministic_hyde_generator():
    generator = DeterministicHyDEGenerator()

    # Conceptual/security query
    doc1 = await generator.generate(
        "How does the cloud architecture protect customer data?"
    )
    assert isinstance(doc1, HypotheticalDocument)
    assert doc1.query == "How does the cloud architecture protect customer data?"
    assert len(doc1.hypothetical_text) > 0
    assert (
        "security" in doc1.hypothetical_text.lower()
        or "cloud" in doc1.hypothetical_text.lower()
    )

    # Rate limiting query
    doc2 = await generator.generate(
        "What are the API rate limits for enterprise tenants?"
    )
    assert isinstance(doc2, HypotheticalDocument)
    assert (
        "rate limit" in doc2.hypothetical_text.lower()
        or "tenant" in doc2.hypothetical_text.lower()
    )

    # Fallback query
    doc3 = await generator.generate("General miscellaneous query")
    assert isinstance(doc3, HypotheticalDocument)
    assert len(doc3.hypothetical_text) > 0


@pytest.mark.asyncio
async def test_safe_hyde_executor_success():
    mock_generator = MagicMock(spec=DeterministicHyDEGenerator)
    mock_generator.generate = AsyncMock(
        return_value=HypotheticalDocument(
            query="test query",
            hypothetical_text="This is a hypothetical document about multi-tenant security.",
            provider="deterministic",
            token_count=12,
        )
    )

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.generate_embeddings = AsyncMock(return_value=[[0.1] * 768])

    doc_id = uuid4()
    chunk_id = uuid4()
    real_chunk = RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        document_name="cloud_architecture.md",
        chunk_index=0,
        text="Real retrieved chunk from database.",
        similarity_score=0.88,
    )

    mock_dense_retriever = MagicMock(spec=DenseRetriever)
    mock_dense_retriever.retrieve = AsyncMock(return_value=[real_chunk])

    executor = SafeHyDEExecutor(
        hyde_generator=mock_generator,
        embedding_generator=mock_embedder,
        dense_retriever=mock_dense_retriever,
        timeout_ms=1000,
    )

    user_id = uuid4()
    real_chunks, hypo_doc, latency = await executor.execute_hyde_dense_retrieval(
        query="test query",
        user_id=user_id,
        top_k=5,
    )

    assert len(real_chunks) == 1
    assert real_chunks[0].document_name == "cloud_architecture.md"
    assert real_chunks[0].text == "Real retrieved chunk from database."
    # INVARIANT: Hypothetical document content MUST NOT be returned in retrieved_chunks
    assert "hypothetical document" not in real_chunks[0].text
    assert hypo_doc is not None
    assert hypo_doc.token_count == 12


@pytest.mark.asyncio
async def test_safe_hyde_executor_timeout_and_fallback():
    mock_generator = MagicMock()

    async def _slow_gen(*args, **kwargs):
        await asyncio.sleep(0.5)
        return HypotheticalDocument(query="test", hypothetical_text="slow hypo")

    mock_generator.generate = _slow_gen

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.generate_embeddings = AsyncMock(return_value=[[0.1] * 768])

    real_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="fallback_doc.md",
        chunk_index=0,
        text="Fallback direct search result.",
        similarity_score=0.75,
    )
    mock_dense_retriever = MagicMock(spec=DenseRetriever)
    mock_dense_retriever.retrieve = AsyncMock(return_value=[real_chunk])

    # 50ms timeout to force timeout fallback
    executor = SafeHyDEExecutor(
        hyde_generator=mock_generator,
        embedding_generator=mock_embedder,
        dense_retriever=mock_dense_retriever,
        timeout_ms=50,
    )

    fallback_chunks, hypo_doc, latency = await executor.execute_hyde_dense_retrieval(
        query="test query",
        user_id=uuid4(),
        top_k=5,
    )

    assert len(fallback_chunks) == 1
    assert fallback_chunks[0].document_name == "fallback_doc.md"
    # dense_retriever called with fallback query
    assert mock_dense_retriever.retrieve.call_count >= 1


@pytest.mark.asyncio
async def test_llm_hyde_generator_live_and_fallback():
    from app.chat.domain.interfaces import LLMProvider, ProviderResponse, Usage
    from app.documents.services.hyde import LLMHyDEGenerator

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate = AsyncMock(
        return_value=ProviderResponse(
            content=(
                "The cloud infrastructure utilizes multi-AZ Aurora PostgreSQL clusters "
                "with automated KMS AES-256 encryption at rest and mTLS for data in transit."
            ),
            usage=Usage(prompt_tokens=40, completion_tokens=30, total_tokens=70),
        )
    )

    llm_hyde_gen = LLMHyDEGenerator(
        llm_generation_service=mock_llm,
        model="gemini-2.5-flash-lite",
        timeout_ms=500,
        max_retries=1,
    )

    # 1. Successful LLM generation
    doc = await llm_hyde_gen.generate(
        "How is data encrypted in the cloud infrastructure?"
    )
    assert isinstance(doc, HypotheticalDocument)
    assert doc.provider == "llm"
    assert doc.token_count > 0
    assert (
        "encryption" in doc.hypothetical_text.lower()
        or "kms" in doc.hypothetical_text.lower()
    )

    # 2. LLM failure fallback to DeterministicHyDEGenerator
    failing_llm = MagicMock(spec=LLMProvider)
    failing_llm.generate = AsyncMock(side_effect=RuntimeError("API quota exceeded"))
    fallback_hyde_gen = LLMHyDEGenerator(
        llm_generation_service=failing_llm,
        timeout_ms=100,
        max_retries=0,
    )
    fallback_doc = await fallback_hyde_gen.generate(
        "What is the enterprise availability SLO?"
    )
    assert isinstance(fallback_doc, HypotheticalDocument)
    assert fallback_doc.provider == "deterministic"
    assert len(fallback_doc.hypothetical_text) > 0


@pytest.mark.asyncio
async def test_hyde_boundary_security_never_exposes_hypothetical_as_evidence():
    """
    CRITICAL INVARIANT: Hypothetical document content MUST NOT leak into
    citations or evidence pool.
    """
    mock_hyde_gen = MagicMock()
    mock_hyde_gen.generate = AsyncMock(
        return_value=HypotheticalDocument(
            query="test query",
            hypothetical_text="HALLUCINATED FAKE PASSAGE: Secret revenue is 999 Trillion dollars.",
            provider="llm",
            token_count=10,
        )
    )

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.generate_embeddings = AsyncMock(return_value=[[0.05] * 768])

    doc_id = uuid4()
    real_chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=doc_id,
        document_name="financial_report_2025.md",
        chunk_index=0,
        text="Total consolidated GAAP revenue reached $142.5 million in FY2025.",
        similarity_score=0.91,
    )

    mock_dense_retriever = MagicMock(spec=DenseRetriever)
    mock_dense_retriever.retrieve = AsyncMock(return_value=[real_chunk])

    executor = SafeHyDEExecutor(
        hyde_generator=mock_hyde_gen,
        embedding_generator=mock_embedder,
        dense_retriever=mock_dense_retriever,
    )

    real_chunks, hypo_doc, latency = await executor.execute_hyde_dense_retrieval(
        query="What was FY2025 revenue?",
        user_id=uuid4(),
        top_k=5,
    )

    assert len(real_chunks) == 1
    assert "999 Trillion" not in real_chunks[0].text
    assert (
        real_chunks[0].text
        == "Total consolidated GAAP revenue reached $142.5 million in FY2025."
    )
    assert real_chunks[0].document_name == "financial_report_2025.md"
