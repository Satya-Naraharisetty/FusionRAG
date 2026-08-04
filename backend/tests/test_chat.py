import json
from uuid import uuid4

import pytest
from fastapi import status

from app.api.dependencies import get_answer_generation_service, get_current_user_context
from app.chat.domain.exceptions import (
    LLMProviderError,
    NoRelevantContext,
    PromptTooLarge,
    TokenBudgetExceeded,
)
from app.chat.domain.models import AnswerResponse, ChatMessage, Citation, Usage
from app.chat.services.context_builder import ContextBuilder
from app.chat.services.prompt_builder import PromptBuilder
from app.chat.services.token_estimator import CharacterTokenEstimator
from app.chat.services.answer_generation_service import AnswerGenerationService
from app.documents.domain.models import RetrievedChunk, SearchResult
from app.main import app


# --- 1. TokenEstimator Tests ---
def test_character_token_estimator():
    estimator = CharacterTokenEstimator()
    assert estimator.estimate("") == 0
    assert estimator.estimate("a") == 1
    assert estimator.estimate("abcd") == 1
    assert estimator.estimate("abcdefgh") == 2


# --- 2. ContextBuilder Tests ---
def test_context_builder_deduplication_and_ordering():
    estimator = CharacterTokenEstimator()
    builder = ContextBuilder(token_estimator=estimator, max_context_tokens=1000)

    doc_id = uuid4()
    chunk1_id = uuid4()
    chunk2_id = uuid4()

    chunks = [
        RetrievedChunk(
            chunk_id=chunk1_id,
            document_id=doc_id,
            document_name="doc.txt",
            text="First unique chunk content",
            similarity_score=0.8,
            normalized_score=0.9,
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=chunk1_id,  # duplicate
            document_id=doc_id,
            document_name="doc.txt",
            text="First unique chunk content duplicate text",
            similarity_score=0.75,
            normalized_score=0.875,
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=chunk2_id,
            document_id=doc_id,
            document_name="doc.txt",
            text="Second unique chunk content",
            similarity_score=0.7,
            normalized_score=0.85,
            chunk_index=1,
        ),
    ]

    context = builder.build_context(chunks)
    assert len(context.chunk_references) == 2
    assert context.chunk_references[0].chunk_id == chunk1_id
    assert context.chunk_references[1].chunk_id == chunk2_id

    # Verify sequential renumbering in context text
    assert "[Chunk 1]" in context.concatenated_context
    assert "[Chunk 2]" in context.concatenated_context
    # Check that it renumbers sequentially starting from 1
    lines = context.concatenated_context.splitlines()
    assert lines[0].startswith("[Chunk 1] Document: doc.txt")
    assert any(line.startswith("[Chunk 2] Document: doc.txt") for line in lines)


def test_context_builder_truncation():
    estimator = CharacterTokenEstimator()
    # Tiny token budget to force truncation (e.g. 15 characters -> 3 tokens)
    builder = ContextBuilder(token_estimator=estimator, max_context_tokens=15)

    doc_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="Chunk one is medium sized text.",
            similarity_score=0.9,
            normalized_score=0.95,
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_name="doc.txt",
            text="Chunk two is also medium sized.",
            similarity_score=0.8,
            normalized_score=0.9,
            chunk_index=1,
        ),
    ]

    context = builder.build_context(chunks)
    # The first formatted chunk is: "[Chunk 1] Document: doc.txt (ID: ...)\nChunk one is..." which exceeds 15 context tokens.
    # Therefore, even the first chunk might exceed budget if budget is very tiny. Let's verify it gets omitted.
    assert len(context.chunk_references) == 0


# --- 3. PromptBuilder Tests ---
def test_prompt_builder_caching_and_messages(tmp_path):
    # Setup prompt file
    prompt_file = tmp_path / "sys_prompt.txt"
    prompt_file.write_text("Custom system instruction template.", encoding="utf-8")

    builder = PromptBuilder(system_prompt_path=str(prompt_file))
    assert builder.get_system_prompt() == "Custom system instruction template."

    messages = builder.build_messages(question="What is RAG?", context="RAG content text.")
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "Custom system instruction template."
    assert "What is RAG?" in messages[1].content
    assert "RAG content text." in messages[1].content


# --- 4. AnswerGenerationService Tests ---
class MockRetrievalService:
    def __init__(self, chunks=None):
        self.chunks = chunks or []

    async def retrieve(self, query, user_id, top_k, document_ids=None, filter_metadata=None):
        return SearchResult(
            original_query=query,
            retrieval_time=0.005,
            total_matches=len(self.chunks),
            retrieved_chunks=self.chunks,
        )


class MockLLMProvider:
    def __init__(self, response_text="Mocked Answer", usage=None):
        self.response_text = response_text
        self.usage = usage or Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    async def generate(self, messages, model, temperature, max_tokens):
        return self.response_text, self.usage

    async def stream(self, messages, model, temperature, max_tokens):
        # yields two text deltas and final usage
        yield "Mocked ", None
        yield "Answer", self.usage


class MockMessageRepository:
    async def create_assistant_message(self, conversation_id, message_id, role, content=""):
        from app.chat.domain.models import ConversationMessage, MessageRole, MessageStatus
        from datetime import datetime, UTC
        return ConversationMessage(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=MessageStatus.PENDING,
            created_at=datetime.now(UTC),
        )

    async def fail_message(self, message_id, error_message=None):
        pass


class MockConversationManager:
    def __init__(self):
        self._message_repo = MockMessageRepository()

    async def get_or_create_conversation(self, conversation_id, user_id):
        from app.chat.domain.models import Conversation, ConversationState
        from datetime import datetime, UTC
        from uuid import uuid4
        return Conversation(
            id=conversation_id or uuid4(),
            user_id=user_id,
            title="Mock Conversation",
            state=ConversationState.ACTIVE,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_message_at=datetime.now(UTC),
        )

    async def finalize_message(self, conversation_id, message_id, assistant_content, prompt_tokens, completion_tokens, citations=None):
        pass


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:AnswerGenerationService is deprecated:DeprecationWarning")
async def test_answer_generation_service_success():
    doc_id = uuid4()
    chunk_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            document_name="doc.txt",
            text="Context chunk text.",
            similarity_score=0.9,
            normalized_score=0.95,
            chunk_index=0,
        )
    ]

    retrieval_service = MockRetrievalService(chunks)
    estimator = CharacterTokenEstimator()
    from app.chat.services.conversation_context_builder import ConversationContextBuilder
    context_builder = ConversationContextBuilder()
    prompt_builder = PromptBuilder("")
    llm_provider = MockLLMProvider()

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
        token_estimator=estimator,
        conversation_manager=MockConversationManager(),
        model="gpt-4o-mini",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=False,
    )

    response = await service.generate_answer("How are you?", uuid4(), 10)
    assert response.answer == "Mocked Answer"
    assert len(response.citations) == 1
    assert response.citations[0].chunk_id == chunk_id
    assert response.citations[0].document_name == "doc.txt"
    assert response.model == "gpt-4o-mini"
    assert response.usage.prompt_tokens == 10


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:AnswerGenerationService is deprecated:DeprecationWarning")
async def test_answer_generation_service_empty_retrieval():
    retrieval_service = MockRetrievalService([])
    estimator = CharacterTokenEstimator()
    from app.chat.services.conversation_context_builder import ConversationContextBuilder
    context_builder = ConversationContextBuilder()
    prompt_builder = PromptBuilder("")
    llm_provider = MockLLMProvider()

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
        token_estimator=estimator,
        conversation_manager=MockConversationManager(),
        model="gpt-4o-mini",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=False,
    )

    with pytest.raises(NoRelevantContext):
        await service.generate_answer("How are you?", uuid4(), 10)


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:AnswerGenerationService is deprecated:DeprecationWarning")
async def test_answer_generation_service_budget_violations():
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="doc.txt",
            text="Context chunk text.",
            similarity_score=0.9,
            normalized_score=0.95,
            chunk_index=0,
        )
    ]
    retrieval_service = MockRetrievalService(chunks)
    estimator = CharacterTokenEstimator()
    from app.chat.services.conversation_context_builder import ConversationContextBuilder
    context_builder = ConversationContextBuilder()
    prompt_builder = PromptBuilder("")
    llm_provider = MockLLMProvider()

    # Case 1: System Prompt Exceeds Limit
    service_sys_limit = AnswerGenerationService(
        retrieval_service=retrieval_service,
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
        token_estimator=estimator,
        conversation_manager=MockConversationManager(),
        model="gpt-4o-mini",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=5,  # Tiny system prompt budget
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=False,
    )
    with pytest.raises(TokenBudgetExceeded):
        await service_sys_limit.generate_answer("How are you?", uuid4(), 10)

    # Case 2: Total Prompt Too Large
    service_total_limit = AnswerGenerationService(
        retrieval_service=retrieval_service,
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
        token_estimator=estimator,
        conversation_manager=MockConversationManager(),
        model="gpt-4o-mini",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=False,
    )
    long_question = "a" * 8000  # 2000 tokens
    with pytest.raises(PromptTooLarge):
        await service_total_limit.generate_answer(long_question, uuid4(), 10)


# --- 5. API Endpoint Tests ---
@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


def test_api_chat_success(client):
    doc_id = uuid4()
    chunk_id = uuid4()
    mock_response = AnswerResponse(
        answer="Hello there!",
        citations=[
            Citation(
                document_id=doc_id,
                document_name="test.txt",
                chunk_id=chunk_id,
                chunk_index=0,
            )
        ],
        retrieval_time_ms=10.0,
        generation_time_ms=150.0,
        total_time_ms=160.0,
        model="gpt-4o-mini",
        usage=Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
    )

    class MockAnswerServiceSync:
        async def generate_answer(self, question, user_id, top_k, conversation_id=None, document_ids=None, filters=None):
            return mock_response

    # Setup overrides
    mock_user_id = uuid4()
    app.dependency_overrides[get_current_user_context] = lambda: {"user_id": str(mock_user_id), "role": "user"}
    app.dependency_overrides[get_answer_generation_service] = lambda: MockAnswerServiceSync()

    payload = {
        "question": "What is RAG?",
        "document_ids": [str(doc_id)],
        "top_k": 5,
        "filters": {},
        "stream": False,
    }

    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["answer"] == "Hello there!"
    assert len(data["citations"]) == 1
    assert data["citations"][0]["chunk_id"] == str(chunk_id)
    assert data["usage"]["total_tokens"] == 30


def test_api_chat_streaming(client):
    doc_id = uuid4()
    chunk_id = uuid4()

    async def mock_stream_generator(question, user_id, top_k, conversation_id=None, document_ids=None, filters=None):
        yield {
            "event": "metadata",
            "data": {
                "citations": [
                    {
                        "document_id": str(doc_id),
                        "document_name": "test.txt",
                        "chunk_id": str(chunk_id),
                        "chunk_index": 0,
                    }
                ],
                "retrieval_time_ms": 10.0,
            },
        }
        yield {
            "event": "text",
            "data": {
                "text": "Hello ",
            },
        }
        yield {
            "event": "text",
            "data": {
                "text": "world!",
            },
        }
        yield {
            "event": "done",
            "data": {
                "answer": "Hello world!",
                "citations": [
                    {
                        "document_id": str(doc_id),
                        "document_name": "test.txt",
                        "chunk_id": str(chunk_id),
                        "chunk_index": 0,
                    }
                ],
                "generation_time_ms": 100.0,
                "total_time_ms": 110.0,
                "model": "gpt-4o-mini",
                "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
            },
        }

    class MockAnswerServiceStream:
        def generate_answer_stream(self, question, user_id, top_k, conversation_id=None, document_ids=None, filters=None):
            return mock_stream_generator(question, user_id, top_k, conversation_id, document_ids, filters)

    mock_user_id = uuid4()
    app.dependency_overrides[get_current_user_context] = lambda: {"user_id": str(mock_user_id), "role": "user"}
    app.dependency_overrides[get_answer_generation_service] = lambda: MockAnswerServiceStream()

    payload = {
        "question": "Say hello world",
        "stream": True,
    }

    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers["content-type"]

    lines = response.text.split("\n")
    events = [line for line in lines if line.strip()]

    # We expect 4 event + data chunks
    assert len(events) == 8  # 4 events, 4 data rows
    assert "event: metadata" in events[0]
    assert "event: text" in events[2]
    assert "event: text" in events[4]
    assert "event: done" in events[6]


def test_api_chat_exceptions(client):
    class MockAnswerServiceExceptions:
        async def generate_answer(self, question, user_id, top_k, conversation_id=None, document_ids=None, filters=None):
            raise NoRelevantContext("Empty database context.")

    app.dependency_overrides[get_current_user_context] = lambda: {"user_id": str(uuid4()), "role": "user"}
    app.dependency_overrides[get_answer_generation_service] = lambda: MockAnswerServiceExceptions()

    payload = {"question": "What is RAG?"}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "NO_RELEVANT_CONTEXT"
