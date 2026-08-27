from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.chat.services.chat_orchestrator import ChatOrchestrator
from app.documents.domain.models import RetrievedChunk, SearchResult


@pytest.mark.asyncio
async def test_chat_orchestration_trace_hierarchy():
    from app.core.telemetry import set_tracer_provider_for_test

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider_for_test(provider)

    try:
        mock_conv_mgr = AsyncMock()
        conv_id = uuid4()
        user_id = uuid4()

        mock_conv = MagicMock()
        mock_conv.id = conv_id
        mock_conv_mgr.get_or_create_conversation.return_value = mock_conv

        mock_ctx = MagicMock()
        mock_ctx.recent_messages = []
        mock_ctx.summary = None
        mock_rewrite = MagicMock()
        mock_rewrite.rewritten_query = "What is Hybrid RAG?"
        mock_rewrite.rewrite_applied = False
        mock_rewrite.rewrite_reason = "No history"
        mock_conv_mgr.prepare_context.return_value = (mock_ctx, mock_rewrite)

        mock_retrieval = AsyncMock()
        mock_retrieval.retrieve.return_value = SearchResult(
            original_query="What is Hybrid RAG?",
            retrieval_time=0.05,
            total_matches=1,
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    document_name="doc1.pdf",
                    text="Hybrid RAG combines dense and sparse search.",
                    similarity_score=0.9,
                    normalized_score=0.9,
                    metadata={},
                    chunk_index=0,
                )
            ],
            dense_matches=[],
            sparse_matches=[],
        )

        mock_prompt_builder = MagicMock()
        mock_prompt_builder.get_system_prompt.return_value = "System prompt"
        mock_prompt_builder.build_prompt.return_value = (
            [{"role": "user", "content": "What is Hybrid RAG?"}],
            mock_retrieval.retrieve.return_value.retrieved_chunks,
        )

        mock_token_estimator = MagicMock()
        mock_token_estimator.estimate.return_value = 50

        mock_context_builder = MagicMock()
        mock_context_builder.build_context.return_value = MagicMock()

        from app.chat.domain.interfaces import ProviderResponse
        from app.chat.domain.models import AnswerResponse, Usage

        mock_llm_service = AsyncMock()
        mock_llm_service.generate.return_value = ProviderResponse(
            content="Hybrid RAG is a search paradigm.",
            usage=Usage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        )

        orchestrator = ChatOrchestrator(
            conversation_manager=mock_conv_mgr,
            retrieval_service=mock_retrieval,
            prompt_builder=mock_prompt_builder,
            context_builder=mock_context_builder,
            token_estimator=mock_token_estimator,
            llm_generation_service=mock_llm_service,
            agent_executor=AsyncMock(),
            model="gpt-4o-mini",
            enable_conversation_memory=True,
            enable_tool_calling=False,
        )

        resp = await orchestrator.generate_answer(
            question="What is Hybrid RAG?",
            user_id=user_id,
            top_k=5,
            conversation_id=conv_id,
            document_ids=[uuid4()],
        )

        assert isinstance(resp, AnswerResponse)
        spans = exporter.get_finished_spans()
        span_names = [s.name for s in spans]

        assert "rag.chat_orchestration" in span_names
        assert "conversation.prepare_context" in span_names
        assert "rag.build_prompt" in span_names
    finally:
        set_tracer_provider_for_test(None)
