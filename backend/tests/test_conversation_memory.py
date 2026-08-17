from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import (
    get_chat_orchestrator,
    get_conversation_manager,
)
from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.chat.domain.exceptions import (
    ConversationConcurrentUpdateException,
    ConversationNotFoundException,
    InvalidStatusTransitionException,
    UnauthorizedConversationAccessException,
)
from app.chat.domain.models import (
    ChatRole,
    Conversation,
    ConversationMessage,
    ConversationState,
    ConversationSummary,
    HistoryRewriteResult,
    MessageRole,
    MessageStatus,
    RetrievalDiagnostics,
    Usage,
)
from app.chat.infrastructure.cache import MemoryRewriteCache
from app.chat.infrastructure.persistence.repositories import (
    SQLAlchemyConversationRepository,
    SQLAlchemyMessageRepository,
    SQLAlchemySummaryRepository,
)
from app.chat.services.access_service import ConversationAccessService
from app.chat.services.answer_generation_service import AnswerGenerationService
from app.chat.services.conversation_context_builder import ConversationContextBuilder
from app.chat.services.conversation_manager import ConversationManager
from app.chat.services.conversation_summarizer import LLMConversationSummarizer
from app.chat.services.history_rewriter import LLMHistoryRewriter
from app.chat.services.prompt_builder import PromptBuilder
from app.chat.services.rolling_memory import RollingConversationMemory
from app.chat.services.token_estimator import CharacterTokenEstimator
from app.db.models import Base
from app.documents.domain.models import RetrievedChunk, SearchResult
from tests.db import TEST_DATABASE_URL


@pytest.fixture(scope="function")
def chat_test_db(client):
    """
    Sets up a clean database for conversation memory tests.
    """
    engine = create_engine(TEST_DATABASE_URL)
    try:
        Base.metadata.create_all(bind=engine)

        session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        db = session_local()
        try:
            db.execute(text("TRUNCATE TABLE conversation_summaries CASCADE;"))
            db.execute(text("TRUNCATE TABLE conversation_messages CASCADE;"))
            db.execute(text("TRUNCATE TABLE conversations CASCADE;"))
            db.execute(text("TRUNCATE TABLE refresh_sessions CASCADE;"))
            db.execute(text("TRUNCATE TABLE users CASCADE;"))
            db.commit()
        finally:
            db.close()

        client.app.state.db_session_factory = session_local
        yield session_local
    finally:
        engine.dispose()


@pytest.fixture(scope="function")
def test_users(chat_test_db):
    """
    Registers two test users in the database to satisfy foreign keys.
    """
    db = chat_test_db()

    user1 = SQLAlchemyUser(
        id=uuid4(),
        email=f"test_1_{uuid4()}@example.com",
        hashed_password="hashedpassword123",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    user2 = SQLAlchemyUser(
        id=uuid4(),
        email=f"test_2_{uuid4()}@example.com",
        hashed_password="hashedpassword123",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user1)
    db.add(user2)
    db.commit()

    user1_id, user2_id = user1.id, user2.id
    db.close()
    return user1_id, user2_id


# Helper function to register and authenticate a user
def get_user_token_and_id(
    client, email="chat_user@example.com", password="SecurePassword123!"
):
    # Register
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    user_id = reg_resp.json()["id"]
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response.json()["access_token"], UUID(user_id)


class MockLLMProvider:
    def __init__(self, response_text="Mocked Answer", usage=None):
        self.response_text = response_text
        self.usage = usage or Usage(
            prompt_tokens=10, completion_tokens=5, total_tokens=15
        )
        self.last_messages = []

    async def generate(self, messages, model, temperature, max_tokens):
        self.last_messages = messages
        return self.response_text, self.usage

    async def stream(self, messages, model, temperature, max_tokens):
        self.last_messages = messages
        yield "Mocked ", None
        yield "Answer", self.usage


class MockRetrievalService:
    def __init__(self, chunks=None, user_has_chunks=True):
        self.chunks = chunks or []
        self._user_has_chunks = user_has_chunks
        self.retrieve_calls = 0

    async def user_has_chunks(self, user_id):
        return self._user_has_chunks

    async def retrieve(
        self,
        query,
        user_id,
        top_k,
        document_ids=None,
        filter_metadata=None,
        tags=None,
        retrieval_mode=None,
        retrieval_scope=None,
    ):
        self.retrieve_calls += 1
        return SearchResult(
            original_query=query,
            retrieval_time=0.01,
            total_matches=len(self.chunks),
            retrieved_chunks=self.chunks,
            dense_matches=self.chunks,
            sparse_matches=self.chunks,
        )


# --- 1. Repository & Access Control Unit Tests ---


@pytest.mark.asyncio
async def test_conversation_repository_crud(chat_test_db, test_users):
    db = chat_test_db()
    repo = SQLAlchemyConversationRepository(db)
    user_id, _ = test_users
    conv_id = uuid4()

    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Initial Title",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )

    # Create
    created = await repo.create_conversation(conv)
    assert created.id == conv_id
    assert created.title == "Initial Title"

    # Get
    fetched = await repo.get_conversation(conv_id)
    assert fetched is not None
    assert fetched.title == "Initial Title"

    # Update (optimistic locking check)
    fetched.title = "Updated Title"
    updated = await repo.update_conversation(fetched)
    assert updated.title == "Updated Title"
    assert updated.version == 2  # Automatically incremented by version_id_col
    db.commit()

    # Concurrent update check
    fetched_stale = await repo.get_conversation(conv_id)

    # Simulate concurrent update in a separate database connection transaction
    engine = db.bind
    with engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE conversations SET version = 3, title = 'External Update' WHERE id = :id"
            ),
            {"id": conv_id},
        )
        conn.commit()

    # Since fetched_stale has version=2, trying to update it will fail because DB has version=3
    fetched_stale.title = "Stale Update Attempt"
    with pytest.raises(ConversationConcurrentUpdateException):
        await repo.update_conversation(fetched_stale)

    # Soft Delete
    await repo.delete_conversation(conv_id)
    fetched_deleted = await repo.get_conversation(conv_id)
    assert fetched_deleted.state == ConversationState.DELETED

    # List
    active_conv_id = uuid4()
    active_conv = Conversation(
        id=active_conv_id,
        user_id=user_id,
        title="Active Conv",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await repo.create_conversation(active_conv)
    listed = await repo.list_conversations(user_id)
    assert len(listed) == 1  # Only ACTIVE, not DELETED
    assert listed[0].id == active_conv_id

    db.close()


@pytest.mark.asyncio
async def test_conversation_access_service(chat_test_db, test_users):
    db = chat_test_db()
    repo = SQLAlchemyConversationRepository(db)
    access_service = ConversationAccessService(repo)

    user1, user2 = test_users
    conv_id = uuid4()

    conv = Conversation(
        id=conv_id,
        user_id=user1,
        title="User 1 Conversation",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await repo.create_conversation(conv)

    # Verify Owner Success
    await access_service.verify_owner(conv_id, user1)

    # Verify Owner Unauthorized
    with pytest.raises(UnauthorizedConversationAccessException):
        await access_service.verify_owner(conv_id, user2)

    # Verify Not Found
    with pytest.raises(ConversationNotFoundException):
        await access_service.verify_owner(uuid4(), user1)

    db.close()


# --- 2. Message Repository Unit Tests ---


@pytest.mark.asyncio
async def test_message_repository_lifecycle(chat_test_db, test_users):
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    user_id, _ = test_users

    conv_id = uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Chat",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await conv_repo.create_conversation(conv)

    # User message addition
    user_msg_id = uuid4()
    user_msg = ConversationMessage(
        id=user_msg_id,
        conversation_id=conv_id,
        role=MessageRole.USER,
        content="Hello!",
        status=MessageStatus.COMPLETED,
        created_at=datetime.now(UTC),
    )
    await msg_repo.add_message(user_msg)

    # Assistant streaming message lifecycle
    assistant_msg_id = uuid4()
    await msg_repo.create_assistant_message(
        conv_id, assistant_msg_id, MessageRole.ASSISTANT
    )

    # Verify PENDING status
    messages = await msg_repo.get_recent_messages(conv_id, limit=10)
    assistant_loaded = next(m for m in messages if m.id == assistant_msg_id)
    assert assistant_loaded.status == MessageStatus.PENDING

    # Append stream chunk
    await msg_repo.append_stream_chunk(assistant_msg_id, "chunk 1")
    await msg_repo.append_stream_chunk(assistant_msg_id, " chunk 2")

    messages = await msg_repo.get_recent_messages(conv_id, limit=10)
    assistant_loaded = next(m for m in messages if m.id == assistant_msg_id)
    assert assistant_loaded.status == MessageStatus.STREAMING
    assert assistant_loaded.content == "chunk 1 chunk 2"

    # Complete message
    citations = [{"chunk_id": str(uuid4())}]
    await msg_repo.complete_message(
        assistant_msg_id, prompt_tokens=10, completion_tokens=20, citations=citations
    )

    messages = await msg_repo.get_recent_messages(conv_id, limit=10)
    assistant_loaded = next(m for m in messages if m.id == assistant_msg_id)
    assert assistant_loaded.status == MessageStatus.COMPLETED
    assert assistant_loaded.citations == citations
    assert assistant_loaded.prompt_tokens == 10
    assert assistant_loaded.completion_tokens == 20

    # Fail message test
    failed_msg_id = uuid4()
    await msg_repo.create_assistant_message(
        conv_id, failed_msg_id, MessageRole.ASSISTANT
    )
    await msg_repo.fail_message(failed_msg_id, "Network timeout error")

    messages = await msg_repo.get_recent_messages(conv_id, limit=10)
    failed_loaded = next(m for m in messages if m.id == failed_msg_id)
    assert failed_loaded.status == MessageStatus.FAILED
    assert failed_loaded.metadata["error_message"] == "Network timeout error"

    # Count
    count = await msg_repo.count_messages(conv_id)
    assert count == 3

    db.close()


# --- 3. Memory Pruning & Summarization Tests ---


@pytest.mark.asyncio
async def test_rolling_conversation_memory(chat_test_db, test_users):
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    sum_repo = SQLAlchemySummaryRepository(db)
    user_id, _ = test_users

    conv_id = uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Chat",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await conv_repo.create_conversation(conv)

    # Create 5 messages
    msg_ids = [uuid4() for _ in range(5)]
    for i, mid in enumerate(msg_ids):
        msg = ConversationMessage(
            id=mid,
            conversation_id=conv_id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"Message {i}",
            status=MessageStatus.COMPLETED,
            created_at=datetime.now(UTC) + timedelta(milliseconds=i),
        )
        await msg_repo.add_message(msg)

    # 1. Without summary, loads recent messages (capped to max_messages)
    memory = RollingConversationMemory(msg_repo, sum_repo, max_messages=3)
    loaded_msgs, loaded_summary = await memory.load_memory(conv_id)
    assert loaded_summary is None
    assert len(loaded_msgs) == 3
    assert loaded_msgs[0].content == "Message 2"
    assert loaded_msgs[2].content == "Message 4"

    # 2. Add summary covering up to message 2 (Message index 2)
    summary_obj = ConversationSummary(
        id=uuid4(),
        conversation_id=conv_id,
        summary="Summary of first 3 messages",
        summary_version=1,
        covered_from_message_id=msg_ids[0],
        covered_until_message_id=msg_ids[2],
        message_count=3,
        created_at=datetime.now(UTC),
    )
    await sum_repo.save_summary(summary_obj)

    # Memory loads summary and only messages AFTER Message 2 (indices 3 and 4)
    loaded_msgs, loaded_summary = await memory.load_memory(conv_id)
    assert loaded_summary is not None
    assert loaded_summary.summary == "Summary of first 3 messages"
    assert len(loaded_msgs) == 2
    assert loaded_msgs[0].content == "Message 3"
    assert loaded_msgs[1].content == "Message 4"

    db.close()


@pytest.mark.asyncio
async def test_conversation_summarizer(chat_test_db, test_users):
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    sum_repo = SQLAlchemySummaryRepository(db)
    user_id, _ = test_users

    conv_id = uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Chat",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await conv_repo.create_conversation(conv)

    # Add messages
    msg_ids = []
    for i in range(5):
        mid = uuid4()
        msg_ids.append(mid)
        msg = ConversationMessage(
            id=mid,
            conversation_id=conv_id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"Exchange {i}",
            status=MessageStatus.COMPLETED,
            created_at=datetime.now(UTC) + timedelta(milliseconds=i),
        )
        await msg_repo.add_message(msg)

    llm_provider = MockLLMProvider("Consolidated rolling summary text.")
    summarizer = LLMConversationSummarizer(
        llm_provider=llm_provider,
        summary_repo=sum_repo,
        message_repo=msg_repo,
        model="gemini-2.5-flash-lite",
    )

    # Generate initial summary up to message index 2
    summary = await summarizer.summarize(conv_id, msg_ids[2])
    assert summary.summary == "Consolidated rolling summary text."
    assert summary.summary_version == 1
    assert summary.covered_from_message_id == msg_ids[0]
    assert summary.covered_until_message_id == msg_ids[2]

    # Generate second summary up to message index 4
    summary2 = await summarizer.summarize(conv_id, msg_ids[4])
    assert summary2.summary_version == 2
    assert summary2.covered_from_message_id == msg_ids[0]
    assert summary2.covered_until_message_id == msg_ids[4]

    db.close()


# --- 4. Query Rewriter Caching & Heuristics ---


@pytest.mark.asyncio
async def test_query_rewriter_heuristics_and_caching():
    llm = MockLLMProvider("Standalone rewritten question")
    # Using local memory cache in rewriter
    rewriter = LLMHistoryRewriter(llm, "gemini-2.5-flash-lite", MemoryRewriteCache())

    history = [
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.USER,
            content="Who created Python?",
            created_at=datetime.now(UTC),
        ),
        ConversationMessage(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Guido van Rossum in 1991.",
            created_at=datetime.now(UTC),
        ),
    ]

    # Case 1: Standalone query heuristics (should bypass rewrite)
    res1 = await rewriter.rewrite("What is Java?", history)
    assert res1.rewrite_applied is False
    assert res1.rewritten_query == "What is Java?"

    # Case 2: Context-dependent query (needs rewrite)
    res2 = await rewriter.rewrite("What about Java?", history)
    assert res2.rewrite_applied is True
    assert res2.rewritten_query == "Standalone rewritten question"

    # Case 3: Cache Hit (second identical request retrieves from local cache)
    llm.response_text = "Different query rewrite that should NOT be returned"
    res3 = await rewriter.rewrite("What about Java?", history)
    assert res3.rewrite_applied is True
    assert (
        res3.rewritten_query == "Standalone rewritten question"
    )  # Returned from cache!


# --- 5. Token Budgeting Hierarchy ---


def test_prompt_builder_budgeting():
    builder = PromptBuilder("")
    estimator = CharacterTokenEstimator()

    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        title="Chat",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    recent_messages = [
        ConversationMessage(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="First question here.",
            created_at=datetime.now(UTC),
        ),
        ConversationMessage(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="Answer to first question.",
            created_at=datetime.now(UTC),
        ),
    ]

    summary = ConversationSummary(
        id=uuid4(),
        conversation_id=conversation.id,
        summary="Rolling summary content",
        covered_from_message_id=uuid4(),
        covered_until_message_id=uuid4(),
        message_count=2,
        created_at=datetime.now(UTC),
    )

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="doc.txt",
            text="Chunk text number one.",
            similarity_score=0.9,
            chunk_index=0,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="doc.txt",
            text="Chunk text number two.",
            similarity_score=0.8,
            chunk_index=1,
        ),
    ]

    from app.chat.domain.models import ConversationContext

    context_obj = ConversationContext(
        conversation=conversation,
        recent_messages=recent_messages,
        summary=summary,
        retrieved_chunks=retrieved_chunks,
        diagnostics=RetrievalDiagnostics(),
    )

    # Enforce strict budget, setting a low limit of 150 characters (which translates to roughly 37 tokens)
    # The budget should prioritize System Prompt -> Question -> Summary -> History -> Documents.
    # Documents will be trimmed or skipped to fit.
    messages, final_chunks = builder.build_prompt(
        context_obj=context_obj,
        question="What about Python?",
        token_estimator=estimator,
        max_context_tokens=150,
        max_memory_tokens=50,
    )

    # Verify that the system prompt and user question exist
    assert messages[0].role == ChatRole.SYSTEM
    assert "Rolling summary" in messages[0].content
    assert messages[-1].role == ChatRole.USER
    assert "What about Python?" in messages[-1].content
    # The budget is small, so retrieved document chunks should be pruned/skipped
    assert len(final_chunks) < 2


# --- 5b. Stub document service (two-tier document model) ---


class _StubDocService:
    """Minimal DocumentService stand-in: the orchestrator only reads ``.id``."""

    def __init__(self, doc_id):
        self._doc_id = doc_id

    def list_documents(self, user_id):
        return [type("Doc", (), {"id": self._doc_id})()]

    def list_documents_by_conversation(self, conversation_id, user_id):
        return []


# --- 6. End-to-End RAG Answer Generation Tests ---


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
async def test_answer_generation_service_end_to_end(chat_test_db, test_users):
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    sum_repo = SQLAlchemySummaryRepository(db)
    user_id, _ = test_users

    # Resolving and wiring services
    llm = MockLLMProvider("Direct grounded response.")
    estimator = CharacterTokenEstimator()
    prompt_builder = PromptBuilder("")
    context_builder = ConversationContextBuilder()

    doc_id = uuid4()
    chunk_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            document_name="doc.txt",
            text="Python was created in 1991.",
            similarity_score=0.95,
            chunk_index=0,
        )
    ]
    retrieval_service = MockRetrievalService(chunks)

    conv_id = uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="New Conversation",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await conv_repo.create_conversation(conv)

    # Stub Title Generator
    from app.chat.services.title_generator import FallbackConversationTitleGenerator

    title_generator = FallbackConversationTitleGenerator()

    # Stub event dispatcher
    from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher

    dispatcher = SimpleEventDispatcher()

    access_service = ConversationAccessService(conv_repo)
    memory = RollingConversationMemory(msg_repo, sum_repo, max_messages=12)
    rewriter = LLMHistoryRewriter(llm, "gemini-2.5-flash-lite", MemoryRewriteCache())

    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=sum_repo,
        access_service=access_service,
        memory=memory,
        rewriter=rewriter,
        title_generator=title_generator,
        event_dispatcher=dispatcher,
        document_service=_StubDocService(doc_id),
    )

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-2.5-flash-lite",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )

    # 1. Test generate_answer (Sync). Global documents are only retrieved on
    # the @documents mention (two-tier model), which also exercises the
    # mention-stripping path.
    response = await service.generate_answer(
        question="@documents When was Python created?",
        user_id=user_id,
        top_k=10,
        conversation_id=conv_id,
    )

    assert response.answer == "Direct grounded response."
    assert response.conversation_id == conv_id
    assert response.diagnostics is not None
    assert response.diagnostics.fusion_count == 1
    # Retrieval ran normally (documents exist) — the skip marker stays False.
    assert response.diagnostics.retrieval_skipped is False
    assert len(response.citations) == 1
    assert response.citations[0].document_name == "doc.txt"

    # Confirm message count in database
    count = await msg_repo.count_messages(conv_id)
    assert count == 2  # User question + Assistant reply

    # 2. Test generate_answer_stream (Streaming compatibility)
    events = []
    async for event in service.generate_answer_stream(
        question="@documents What about Java?",
        user_id=user_id,
        top_k=10,
        conversation_id=conv_id,
    ):
        events.append(event)

    assert len(events) >= 3
    assert events[0]["event"] == "metadata"
    assert events[-1]["event"] == "done"
    assert "Mocked Answer" in events[-1]["data"]["answer"]

    # Confirm count updated
    count = await msg_repo.count_messages(conv_id)
    assert count == 4  # 2 more messages added (User + Assistant)

    db.close()


# --- 7. API Router Endpoint Integration Tests ---


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_conversations_api_flow(client, chat_test_db):
    # 1. Setup mock services and configure overrides at start
    db_session = chat_test_db()

    from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher

    dispatcher = SimpleEventDispatcher()

    llm = MockLLMProvider("AI Response Title generator")
    estimator = CharacterTokenEstimator()
    prompt_builder = PromptBuilder("")
    context_builder = ConversationContextBuilder()

    doc_id = uuid4()
    chunk_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            document_name="doc.txt",
            text="Python was created in 1991.",
            similarity_score=0.95,
            chunk_index=0,
        )
    ]
    retrieval_service = MockRetrievalService(chunks)

    conv_repo = SQLAlchemyConversationRepository(db_session)
    msg_repo = SQLAlchemyMessageRepository(db_session)
    sum_repo = SQLAlchemySummaryRepository(db_session)
    access_service = ConversationAccessService(conv_repo)
    memory = RollingConversationMemory(msg_repo, sum_repo, max_messages=12)
    rewriter = LLMHistoryRewriter(llm, "gemini-2.5-flash-lite", MemoryRewriteCache())

    # Title generator
    from app.chat.services.title_generator import FallbackConversationTitleGenerator

    title_generator = FallbackConversationTitleGenerator()

    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=sum_repo,
        access_service=access_service,
        memory=memory,
        rewriter=rewriter,
        title_generator=title_generator,
        event_dispatcher=dispatcher,
        db=db_session,
    )

    real_service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-2.5-flash-lite",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )

    client.app.dependency_overrides[get_chat_orchestrator] = lambda: real_service
    client.app.dependency_overrides[get_conversation_manager] = lambda: manager

    # Setup token & user
    token, user_id = get_user_token_and_id(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. POST /chat to create a new conversation in the DB
    chat_resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "Let's chat!", "stream": False},
    )
    assert chat_resp.status_code == status.HTTP_200_OK
    conv_id = chat_resp.json()["conversation_id"]
    assert conv_id is not None

    # Commit any changes so list endpoint sees them in test transaction isolation
    db_session.commit()

    # 3. Get Paginated Conversations List
    list_resp = client.get("/api/v1/conversations?limit=10&offset=0", headers=headers)
    assert list_resp.status_code == status.HTTP_200_OK
    data = list_resp.json()
    assert len(data["conversations"]) >= 1
    assert data["conversations"][0]["id"] == conv_id
    assert data["conversations"][0]["title"] == "Let's chat!"

    # 4. Patch Title & Settings
    patch_resp = client.patch(
        f"/api/v1/conversations/{conv_id}",
        headers=headers,
        json={
            "title": "Renamed Chat Session",
            "settings": {"temperature": 0.7, "model": "gemini-2.5-flash-lite"},
        },
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    patched_data = patch_resp.json()
    assert patched_data["title"] == "Renamed Chat Session"
    assert patched_data["settings"]["temperature"] == 0.7
    assert patched_data["settings"]["model"] == "gemini-2.5-flash-lite"

    # 5. Get specific conversation details
    detail_resp = client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.json()["title"] == "Renamed Chat Session"

    # 6. Fetch Paginated Messages List
    # First add a second message turn through chat endpoint to continue session
    client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "question": "What is Python?",
            "conversation_id": conv_id,
            "stream": False,
        },
    )
    db_session.commit()

    msgs_resp = client.get(
        f"/api/v1/conversations/{conv_id}/messages?limit=10&offset=0", headers=headers
    )
    assert msgs_resp.status_code == status.HTTP_200_OK
    msgs_data = msgs_resp.json()
    # Should have 4 messages (First User + Assistant, Second User + Assistant)
    assert len(msgs_data["messages"]) == 4
    assert msgs_data["messages"][0]["role"] == "user"
    assert msgs_data["messages"][1]["role"] == "assistant"

    # 7. Delete conversation (soft delete)
    del_resp = client.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert del_resp.status_code == status.HTTP_204_NO_CONTENT
    db_session.commit()

    # Verify conversation is omitted from active list
    list_resp2 = client.get("/api/v1/conversations?limit=10&offset=0", headers=headers)
    assert list_resp2.status_code == status.HTTP_200_OK
    assert len(list_resp2.json()["conversations"]) == 0

    client.app.dependency_overrides.clear()
    db_session.close()


# --- 8. Chat Persistence & Client-Disconnect Handling ---


class IdentityHistoryRewriter:
    """Rewrite stub that never rewrites; keeps tests deterministic."""

    async def rewrite(self, question, history):
        return HistoryRewriteResult(
            original_query=question,
            rewritten_query=question,
            rewrite_reason="test stub",
            rewrite_applied=False,
        )


@pytest.fixture(scope="function")
def real_chat_wiring(client, chat_test_db):
    """
    Wires the real chat dependency graph — real request-scoped get_db session,
    real ConversationManager and real orchestrator — with only the external
    services (LLM, retrieval, titles, rewrites) mocked. Persistence therefore
    depends entirely on the get_db commit at request teardown, which is the
    behavior these regression tests guard.
    """
    db = chat_test_db()

    from app.api.dependencies import (
        get_conversation_title_generator,
        get_document_service,
        get_history_rewriter,
        get_llm_provider,
        get_prompt_builder,
        get_retrieval_service,
    )
    from app.chat.services.title_generator import FallbackConversationTitleGenerator

    llm = MockLLMProvider("Mocked Answer")
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_name="doc.txt",
        text="Python was created in 1991.",
        similarity_score=0.95,
        chunk_index=0,
    )

    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    client.app.dependency_overrides[get_retrieval_service] = lambda: (
        MockRetrievalService([chunk])
    )
    client.app.dependency_overrides[get_history_rewriter] = lambda: (
        IdentityHistoryRewriter()
    )
    client.app.dependency_overrides[get_conversation_title_generator] = lambda: (
        FallbackConversationTitleGenerator()
    )
    client.app.dependency_overrides[get_prompt_builder] = lambda: PromptBuilder("")
    client.app.dependency_overrides[get_document_service] = lambda: None

    yield db

    client.app.dependency_overrides.clear()
    db.close()


def _assert_persisted_turn(client, token, question, *, stream):
    """
    Runs one chat request and asserts conversation + messages persist.

    Critically, no manual db.commit() is ever called: persistence must come
    from get_db's commit at request teardown (regression guard for the chat
    persistence fix). Rows are read through a fresh session.
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": question, "stream": stream},
    )
    assert resp.status_code == status.HTTP_200_OK
    if stream:
        assert "text/event-stream" in resp.headers["content-type"]
        assert "Mocked Answer" in resp.text

    db = client.app.state.db_session_factory()
    try:
        rows = db.execute(
            text(
                "SELECT c.id, m.role, m.status, m.content "
                "FROM conversations c "
                "JOIN conversation_messages m ON m.conversation_id = c.id "
                "ORDER BY m.created_at, m.id"
            )
        ).fetchall()
    finally:
        db.close()

    assert len(rows) == 2, f"expected user + assistant messages, got {len(rows)}"
    roles = [r[1] for r in rows]
    statuses = [r[2] for r in rows]
    contents = [r[3] for r in rows]
    assert roles == ["user", "assistant"]
    assert statuses == ["completed", "completed"]
    assert contents[0] == question
    assert "Mocked Answer" in contents[1]
    return rows[0][0]


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_api_chat_stream_persists_conversation_and_messages(client, real_chat_wiring):
    """
    Regression: after a streaming /chat request, the conversation, the user
    question and the completed assistant answer must be persisted in the DB
    even though no code path calls db.commit() explicitly (get_db owns it).
    """
    token, _user_id = get_user_token_and_id(client)
    conv_id = _assert_persisted_turn(
        client, token, "When was Python created?", stream=True
    )
    assert conv_id is not None


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_api_chat_sync_persists_conversation_and_messages(client, real_chat_wiring):
    """
    Same persistence regression guard for the synchronous (non-streaming) path.
    """
    token, _user_id = get_user_token_and_id(client)
    conv_id = _assert_persisted_turn(
        client, token, "When was Python created?", stream=False
    )
    assert conv_id is not None


def _build_answer_service(db):
    """Builds a real orchestrator stack bound to the given session."""
    from app.chat.services.title_generator import FallbackConversationTitleGenerator
    from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher

    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    sum_repo = SQLAlchemySummaryRepository(db)

    llm = MockLLMProvider("Mocked Answer")
    estimator = CharacterTokenEstimator()
    prompt_builder = PromptBuilder("")
    context_builder = ConversationContextBuilder()
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="doc.txt",
            text="Python was created in 1991.",
            similarity_score=0.95,
            chunk_index=0,
        )
    ]
    retrieval_service = MockRetrievalService(chunks)
    dispatcher = SimpleEventDispatcher()
    access_service = ConversationAccessService(conv_repo)
    memory = RollingConversationMemory(msg_repo, sum_repo, max_messages=12)
    rewriter = LLMHistoryRewriter(llm, "gemini-2.5-flash-lite", MemoryRewriteCache())

    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=sum_repo,
        access_service=access_service,
        memory=memory,
        rewriter=rewriter,
        title_generator=FallbackConversationTitleGenerator(),
        event_dispatcher=dispatcher,
    )

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-2.5-flash-lite",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )
    return service


def _read_messages(db, conversation_id):
    return db.execute(
        text(
            "SELECT role, status, content, metadata "
            "FROM conversation_messages "
            "WHERE conversation_id = :c "
            "ORDER BY created_at, id"
        ),
        {"c": conversation_id},
    ).fetchall()


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
async def test_stream_disconnect_persists_partial_answer_as_interrupted(
    chat_test_db, test_users
):
    """
    When a client disconnects mid-stream (the generator is closed while a
    stream is in flight), the partial assistant answer must be persisted in a
    terminal INTERRUPTED status — not left STREAMING — while the user question
    and conversation remain.
    """
    db = chat_test_db()
    user_id, _ = test_users
    service = _build_answer_service(db)

    agen = service.generate_answer_stream(
        question="When was Python created?", user_id=user_id, top_k=10
    )

    first = await agen.__anext__()
    assert first["event"] == "metadata"
    conv_id = UUID(first["data"]["conversation_id"])

    second = await agen.__anext__()
    assert second["event"] == "text"

    # Client disconnects: closing the async generator delivers GeneratorExit
    # into the orchestrator, which triggers the interrupt sweep.
    await agen.aclose()

    db.commit()
    fresh = chat_test_db()
    try:
        rows = _read_messages(fresh, conv_id)
    finally:
        fresh.close()

    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[0][1] == "completed"
    assert rows[0][2] == "When was Python created?"

    assert rows[1][0] == "assistant"
    assert rows[1][1] == "interrupted"
    assert rows[1][2] == "Mocked "  # partial content preserved
    meta = rows[1][3]
    if isinstance(meta, str):
        import json

        meta = json.loads(meta)
    assert meta.get("interrupt_reason") == "client_disconnected"

    db.close()


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
async def test_stream_disconnect_before_first_chunk_persists_interrupted(
    chat_test_db, test_users
):
    """
    Disconnecting after the metadata event but before any text chunk must still
    leave a terminal INTERRUPTED record (empty partial content), never a PENDING
    message stuck in the DB.
    """
    db = chat_test_db()
    user_id, _ = test_users
    service = _build_answer_service(db)

    agen = service.generate_answer_stream(
        question="When was Python created?", user_id=user_id, top_k=10
    )

    first = await agen.__anext__()
    assert first["event"] == "metadata"
    conv_id = UUID(first["data"]["conversation_id"])

    await agen.aclose()

    db.commit()
    fresh = chat_test_db()
    try:
        rows = _read_messages(fresh, conv_id)
    finally:
        fresh.close()

    assert len(rows) == 2
    assert rows[1][0] == "assistant"
    assert rows[1][1] == "interrupted"
    assert rows[1][2] == ""

    db.close()


@pytest.mark.asyncio
async def test_message_repository_interrupt_lifecycle(chat_test_db, test_users):
    """
    Repo-level coverage of interrupt_message: PENDING/STREAMING -> INTERRUPTED
    with partial content preserved, idempotent no-op on terminal messages, and
    illegal transitions out of INTERRUPTED rejected.
    """
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    user_id, _ = test_users

    conv_id = uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Chat",
        state=ConversationState.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )
    await conv_repo.create_conversation(conv)

    # PENDING -> INTERRUPTED with reason recorded
    pending_id = uuid4()
    await msg_repo.create_assistant_message(conv_id, pending_id, MessageRole.ASSISTANT)
    interrupted = await msg_repo.interrupt_message(
        pending_id, reason="client_disconnected"
    )
    assert interrupted.status == MessageStatus.INTERRUPTED
    assert interrupted.metadata["interrupt_reason"] == "client_disconnected"

    # STREAMING (with partial content) -> INTERRUPTED, content preserved
    streaming_id = uuid4()
    await msg_repo.create_assistant_message(
        conv_id, streaming_id, MessageRole.ASSISTANT
    )
    await msg_repo.append_stream_chunk(streaming_id, "partial ")
    await msg_repo.append_stream_chunk(streaming_id, "answer")
    interrupted2 = await msg_repo.interrupt_message(streaming_id)
    assert interrupted2.status == MessageStatus.INTERRUPTED
    assert interrupted2.content == "partial answer"

    # No-op on already-completed messages
    completed_id = uuid4()
    await msg_repo.create_assistant_message(
        conv_id, completed_id, MessageRole.ASSISTANT
    )
    completed = await msg_repo.complete_message(completed_id, 1, 2)
    noop = await msg_repo.interrupt_message(completed_id)
    assert noop.status == MessageStatus.COMPLETED
    assert completed.status == MessageStatus.COMPLETED

    # Illegal transitions OUT of INTERRUPTED are rejected
    with pytest.raises(InvalidStatusTransitionException):
        await msg_repo.complete_message(pending_id, 1, 2)
    with pytest.raises(InvalidStatusTransitionException):
        await msg_repo.append_stream_chunk(pending_id, "more")
    with pytest.raises(InvalidStatusTransitionException):
        await msg_repo.fail_message(pending_id, "nope")

    db.close()


# --- 9. No-Documents Fallback & @documents Mention ---


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
async def test_answer_generation_skips_rewrite_and_retrieval_without_documents(
    chat_test_db, test_users
):
    """
    When the user has no uploaded documents, the LLM query-rewrite step is
    skipped (no wasted LLM call) and retrieval is skipped entirely — the bot
    answers from general knowledge with empty citations.
    """
    db = chat_test_db()
    conv_repo = SQLAlchemyConversationRepository(db)
    msg_repo = SQLAlchemyMessageRepository(db)
    sum_repo = SQLAlchemySummaryRepository(db)
    user_id, _ = test_users

    llm = MockLLMProvider("General knowledge answer.")
    estimator = CharacterTokenEstimator()
    prompt_builder = PromptBuilder("")
    context_builder = ConversationContextBuilder()

    retrieval_service = MockRetrievalService([], user_has_chunks=False)

    class RecordingRewriter:
        """Fails the test if the rewrite LLM call is ever invoked."""

        def __init__(self):
            self.calls = 0

        async def rewrite(self, question, history):
            self.calls += 1
            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="should not be reached",
                rewrite_applied=True,
            )

    from app.chat.services.title_generator import FallbackConversationTitleGenerator
    from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher

    rewriter = RecordingRewriter()
    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=sum_repo,
        access_service=ConversationAccessService(conv_repo),
        memory=RollingConversationMemory(msg_repo, sum_repo, max_messages=12),
        rewriter=rewriter,
        title_generator=FallbackConversationTitleGenerator(),
        event_dispatcher=SimpleEventDispatcher(),
    )

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-2.5-flash-lite",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )

    response = await service.generate_answer(
        question="Who created Python?", user_id=user_id, top_k=10
    )

    assert response.answer == "General knowledge answer."
    assert response.citations == []
    assert rewriter.calls == 0  # rewrite LLM call skipped
    assert retrieval_service.retrieve_calls == 0  # retrieval skipped
    # The marker tells the frontend this answer came from general knowledge.
    assert response.diagnostics is not None
    assert response.diagnostics.retrieval_skipped is True
    # The fallback prompt relaxes the "ONLY use provided context" rule.
    system_prompt = llm.last_messages[0].content
    assert "general knowledge" in system_prompt

    # The streaming path uses the same skip logic.
    events = []
    async for event in service.generate_answer_stream(
        question="Tell me about the moon.", user_id=user_id, top_k=10
    ):
        events.append(event)

    assert rewriter.calls == 0  # still no rewrite LLM call
    assert retrieval_service.retrieve_calls == 0  # still no retrieval
    assert events[0]["event"] == "metadata"
    assert events[0]["data"]["diagnostics"]["retrieval_skipped"] is True
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["citations"] == []
    assert events[-1]["data"]["diagnostics"]["retrieval_skipped"] is True
    assert "Mocked Answer" in events[-1]["data"]["answer"]

    db.close()


def _override_empty_retrieval(client):
    from app.api.dependencies import get_retrieval_service

    client.app.dependency_overrides[get_retrieval_service] = lambda: (
        MockRetrievalService([])
    )


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_api_chat_without_documents_answers_generally(client, real_chat_wiring):
    """
    No documents uploaded / nothing matched: the chatbot must still answer
    (general-knowledge fallback) with no citations instead of erroring.
    """
    _override_empty_retrieval(client)
    token, _user_id = get_user_token_and_id(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "When was Python created?", "stream": False},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["answer"] == "Mocked Answer"
    assert data["citations"] == []
    # Two-tier model: without the @documents mention (and with no chat-scoped
    # documents), the global knowledge base is NOT searched — the skip marker
    # fires and the bot answers from general knowledge.
    assert data["diagnostics"]["retrieval_skipped"] is True


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_api_chat_stream_without_documents_answers_generally(client, real_chat_wiring):
    """
    Same fallback for the SSE streaming path: done event with a general answer,
    no citations.
    """
    _override_empty_retrieval(client)
    token, _user_id = get_user_token_and_id(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "When was Python created?", "stream": True},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "text/event-stream" in resp.headers["content-type"]
    assert "event: done" in resp.text
    assert "Mocked Answer" in resp.text
    assert "NO_RELEVANT_CONTEXT" not in resp.text


@pytest.mark.filterwarnings(
    "ignore:AnswerGenerationService is deprecated:DeprecationWarning"
)
def test_api_chat_documents_mention_persists_clean_question(client, real_chat_wiring):
    """
    @documents with nothing relevant: the request succeeds, no citations are
    returned, and the persisted user message has the control mention stripped.
    """
    _override_empty_retrieval(client)
    token, _user_id = get_user_token_and_id(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "question": "@documents When was Python created?",
            "stream": False,
        },
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["citations"] == []

    db = client.app.state.db_session_factory()
    try:
        rows = db.execute(
            text("SELECT content FROM conversation_messages ORDER BY created_at, id")
        ).fetchall()
    finally:
        db.close()
    assert len(rows) == 2
    assert rows[0][0] == "When was Python created?"
    assert "@documents" not in rows[0][0]
