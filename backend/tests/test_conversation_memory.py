import asyncio
from datetime import datetime, timedelta, UTC
import json
from uuid import UUID, uuid4
import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import (
    get_answer_generation_service,
    get_current_user_context,
    get_event_dispatcher,
    get_conversation_manager,
)
from app.auth.infrastructure.persistence.models import Base, SQLAlchemyUser
from app.chat.domain.exceptions import (
    ConversationConcurrentUpdateException,
    ConversationNotFoundException,
    UnauthorizedConversationAccessException,
)
from app.chat.domain.models import (
    AnswerResponse,
    ChatRole,
    Conversation,
    ConversationMessage,
    ConversationSettings,
    ConversationState,
    ConversationSummary,
    MessageRole,
    MessageStatus,
    RetrievalDiagnostics,
    Usage,
)
from app.chat.infrastructure.persistence.repositories import (
    SQLAlchemyConversationRepository,
    SQLAlchemyMessageRepository,
    SQLAlchemySummaryRepository,
)
from app.chat.services.access_service import ConversationAccessService
from app.chat.services.conversation_context_builder import ConversationContextBuilder
from app.chat.services.conversation_manager import ConversationManager
from app.chat.services.history_rewriter import LLMHistoryRewriter
from app.chat.infrastructure.cache import MemoryRewriteCache
from app.chat.services.prompt_builder import PromptBuilder
from app.chat.services.rolling_memory import RollingConversationMemory
from app.chat.services.title_generator import LLMConversationTitleGenerator
from app.chat.services.conversation_summarizer import LLMConversationSummarizer
from app.documents.domain.models import RetrievedChunk
from app.chat.services.answer_generation_service import AnswerGenerationService
from app.chat.services.token_estimator import CharacterTokenEstimator
from app.documents.domain.models import SearchResult

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"


@pytest.fixture(scope="function")
def chat_test_db(client):
    """
    Sets up a clean database for conversation memory tests.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE conversation_summaries CASCADE;"))
        db.execute(text("TRUNCATE TABLE conversation_messages CASCADE;"))
        db.execute(text("TRUNCATE TABLE conversations CASCADE;"))
        db.execute(text("TRUNCATE TABLE refresh_sessions CASCADE;"))
        db.execute(text("TRUNCATE TABLE users CASCADE;"))
        db.commit()
    finally:
        db.close()

    client.app.state.db_session_factory = SessionLocal
    yield SessionLocal


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
def get_user_token_and_id(client, email="chat_user@example.com", password="SecurePassword123!"):
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
        self.usage = usage or Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        self.last_messages = []

    async def generate(self, messages, model, temperature, max_tokens):
        self.last_messages = messages
        return self.response_text, self.usage

    async def stream(self, messages, model, temperature, max_tokens):
        self.last_messages = messages
        yield "Mocked ", None
        yield "Answer", self.usage


class MockRetrievalService:
    def __init__(self, chunks):
        self.chunks = chunks

    async def retrieve(self, query, user_id, top_k, document_ids=None, filter_metadata=None, tags=None, retrieval_mode=None):
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
            text("UPDATE conversations SET version = 3, title = 'External Update' WHERE id = :id"),
            {"id": conv_id}
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
    await msg_repo.create_assistant_message(conv_id, assistant_msg_id, MessageRole.ASSISTANT)

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
    await msg_repo.complete_message(assistant_msg_id, prompt_tokens=10, completion_tokens=20, citations=citations)

    messages = await msg_repo.get_recent_messages(conv_id, limit=10)
    assistant_loaded = next(m for m in messages if m.id == assistant_msg_id)
    assert assistant_loaded.status == MessageStatus.COMPLETED
    assert assistant_loaded.citations == citations
    assert assistant_loaded.prompt_tokens == 10
    assert assistant_loaded.completion_tokens == 20

    # Fail message test
    failed_msg_id = uuid4()
    await msg_repo.create_assistant_message(conv_id, failed_msg_id, MessageRole.ASSISTANT)
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
        model="gemini-1.5-flash",
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
    rewriter = LLMHistoryRewriter(llm, "gemini-1.5-flash", MemoryRewriteCache())

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
    assert res3.rewritten_query == "Standalone rewritten question"  # Returned from cache!


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

    from app.chat.domain.models import ConversationContext, RetrievalDiagnostics
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


# --- 6. End-to-End RAG Answer Generation Tests ---

@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:AnswerGenerationService is deprecated:DeprecationWarning")
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
    rewriter = LLMHistoryRewriter(llm, "gemini-1.5-flash", MemoryRewriteCache())

    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=sum_repo,
        access_service=access_service,
        memory=memory,
        rewriter=rewriter,
        title_generator=title_generator,
        event_dispatcher=dispatcher,
    )

    service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-1.5-flash",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )

    # 1. Test generate_answer (Sync)
    response = await service.generate_answer(
        question="When was Python created?",
        user_id=user_id,
        top_k=10,
        conversation_id=conv_id,
    )

    assert response.answer == "Direct grounded response."
    assert response.conversation_id == conv_id
    assert response.diagnostics is not None
    assert response.diagnostics.fusion_count == 1
    assert len(response.citations) == 1
    assert response.citations[0].document_name == "doc.txt"

    # Confirm message count in database
    count = await msg_repo.count_messages(conv_id)
    assert count == 2  # User question + Assistant reply

    # 2. Test generate_answer_stream (Streaming compatibility)
    events = []
    async for event in service.generate_answer_stream(
        question="What about Java?",
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

@pytest.mark.filterwarnings("ignore:AnswerGenerationService is deprecated:DeprecationWarning")
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
    rewriter = LLMHistoryRewriter(llm, "gemini-1.5-flash", MemoryRewriteCache())

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
    )

    real_service = AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm,
        token_estimator=estimator,
        conversation_manager=manager,
        context_builder=context_builder,
        model="gemini-1.5-flash",
        temperature=0.0,
        max_response_tokens=100,
        system_prompt_tokens_limit=500,
        max_context_tokens=1000,
        reserved_completion_tokens=50,
        enable_conversation_memory=True,
    )

    client.app.dependency_overrides[get_answer_generation_service] = lambda: real_service
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
            "settings": {"temperature": 0.7, "model": "gemini-1.5-pro"}
        }
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    patched_data = patch_resp.json()
    assert patched_data["title"] == "Renamed Chat Session"
    assert patched_data["settings"]["temperature"] == 0.7
    assert patched_data["settings"]["model"] == "gemini-1.5-pro"

    # 5. Get specific conversation details
    detail_resp = client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.json()["title"] == "Renamed Chat Session"

    # 6. Fetch Paginated Messages List
    # First add a second message turn through chat endpoint to continue session
    client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "What is Python?", "conversation_id": conv_id, "stream": False},
    )
    db_session.commit()
    
    msgs_resp = client.get(f"/api/v1/conversations/{conv_id}/messages?limit=10&offset=0", headers=headers)
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
