import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_conversation_manager, get_current_user_context
from app.chat.domain.models import (
    Conversation,
    ConversationMessage,
    ConversationMetadata,
    ConversationSettings,
    ConversationState,
    MessageRole,
    MessageStatus,
)
from app.chat.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationRepository,
)
from app.chat.infrastructure.persistence.repositories.message_repository import (
    SQLAlchemyMessageRepository,
)
from app.chat.services.access_service import ConversationAccessService
from app.chat.services.conversation_manager import ConversationManager
from app.core.pagination import (
    CursorDirection,
    CursorSigner,
    InvalidCursorException,
)
from app.db.models import Base as FullBase
from app.main import app
from tests.db import TEST_DATABASE_URL


@pytest.fixture
async def async_db():
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(FullBase.metadata.create_all)
        await conn.execute(text("DELETE FROM conversation_messages;"))
        await conn.execute(text("DELETE FROM conversations;"))
        await conn.execute(text("DELETE FROM users;"))

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        # Create a test user in DB for foreign key constraints
        user_id = uuid4()
        await session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active, is_verified, created_at, updated_at) "
                "VALUES (:id, :email, 'hash', 'user', true, true, now(), now())"
            ),
            {"id": user_id, "email": f"test_{user_id.hex[:8]}@example.com"},
        )
        await session.commit()
        session.user_id = user_id
        yield session

        # Cleanup
        await session.execute(text("DELETE FROM conversation_messages;"))
        await session.execute(text("DELETE FROM conversations;"))
        await session.execute(text("DELETE FROM users;"))
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_cursor_signer_encode_decode_roundtrip():
    user_id = uuid4()
    rec_id = uuid4()
    now = datetime.now(UTC)

    token = CursorSigner.encode(
        created_at=now,
        record_id=rec_id,
        direction=CursorDirection.NEXT,
        resource_type="conv",
        context_id=user_id,
    )

    assert isinstance(token, str)
    assert "." in token

    payload = CursorSigner.decode(
        token=token, expected_resource_type="conv", expected_context_id=user_id
    )

    assert payload.id == str(rec_id)
    assert payload.dir == CursorDirection.NEXT
    assert payload.res == "conv"
    assert payload.ctx == str(user_id)


@pytest.mark.asyncio
async def test_cursor_signer_tampered_signature_rejection():
    user_id = uuid4()
    rec_id = uuid4()
    now = datetime.now(UTC)

    token = CursorSigner.encode(
        created_at=now,
        record_id=rec_id,
        direction=CursorDirection.NEXT,
        resource_type="conv",
        context_id=user_id,
    )

    parts = token.split(".")
    tampered_sig = base64.urlsafe_b64encode(b"0" * 32).decode("ascii").rstrip("=")
    tampered_token = f"{parts[0]}.{tampered_sig}"

    with pytest.raises(InvalidCursorException, match="signature verification failed"):
        CursorSigner.decode(
            token=tampered_token,
            expected_resource_type="conv",
            expected_context_id=user_id,
        )


@pytest.mark.asyncio
async def test_cursor_signer_expired_rejection():
    user_id = uuid4()
    rec_id = uuid4()
    now = datetime.now(UTC)

    # Negative TTL -> immediately expired
    token = CursorSigner.encode(
        created_at=now,
        record_id=rec_id,
        direction=CursorDirection.NEXT,
        resource_type="conv",
        context_id=user_id,
        ttl_seconds=-10,
    )

    with pytest.raises(InvalidCursorException, match="expired"):
        CursorSigner.decode(
            token=token,
            expected_resource_type="conv",
            expected_context_id=user_id,
        )


@pytest.mark.asyncio
async def test_cursor_signer_context_mismatch_rejection():
    user_a = uuid4()
    user_b = uuid4()
    rec_id = uuid4()
    now = datetime.now(UTC)

    token = CursorSigner.encode(
        created_at=now,
        record_id=rec_id,
        direction=CursorDirection.NEXT,
        resource_type="conv",
        context_id=user_a,
    )

    with pytest.raises(InvalidCursorException, match="context mismatch"):
        CursorSigner.decode(
            token=token,
            expected_resource_type="conv",
            expected_context_id=user_b,
        )


@pytest.mark.asyncio
async def test_cursor_signer_resource_mismatch_rejection():
    user_id = uuid4()
    rec_id = uuid4()
    now = datetime.now(UTC)

    token = CursorSigner.encode(
        created_at=now,
        record_id=rec_id,
        direction=CursorDirection.NEXT,
        resource_type="conv",
        context_id=user_id,
    )

    with pytest.raises(InvalidCursorException, match="resource mismatch"):
        CursorSigner.decode(
            token=token,
            expected_resource_type="msg",
            expected_context_id=user_id,
        )


@pytest.mark.asyncio
async def test_conversation_keyset_bidirectional_pagination(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    # Create 5 conversations with distinct timestamps
    base_time = datetime.now(UTC) - timedelta(hours=10)
    created_convs = []
    for i in range(5):
        conv = Conversation(
            id=uuid4(),
            user_id=user_id,
            title=f"Conversation {i + 1}",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=base_time + timedelta(minutes=i * 10),
            updated_at=base_time + timedelta(minutes=i * 10),
            last_message_at=base_time + timedelta(minutes=i * 10),
        )
        saved = await repo.create_conversation(conv)
        created_convs.append(saved)

    # Note: ordered by last_message_at DESC: created_convs[4], [3], [2], [1], [0]
    # Page 1: limit=2
    page1 = await repo.list_conversations(user_id=user_id, limit=2)
    assert len(page1.items) == 2
    assert page1.items[0].id == created_convs[4].id
    assert page1.items[1].id == created_convs[3].id
    assert page1.has_next_page is True
    assert page1.has_prev_page is False
    assert page1.next_cursor is not None
    assert page1.prev_cursor is None

    # Page 2: forward using next_cursor
    page2 = await repo.list_conversations(
        user_id=user_id, limit=2, cursor=page1.next_cursor
    )
    assert len(page2.items) == 2
    assert page2.items[0].id == created_convs[2].id
    assert page2.items[1].id == created_convs[1].id
    assert page2.has_next_page is True
    assert page2.has_prev_page is True
    assert page2.next_cursor is not None
    assert page2.prev_cursor is not None

    # Page 3: forward to the final page
    page3 = await repo.list_conversations(
        user_id=user_id, limit=2, cursor=page2.next_cursor
    )
    assert len(page3.items) == 1
    assert page3.items[0].id == created_convs[0].id
    assert page3.has_next_page is False
    assert page3.has_prev_page is True
    assert page3.next_cursor is None
    assert page3.prev_cursor is not None

    # Backward: from Page 2 using prev_cursor back to Page 1
    page1_back = await repo.list_conversations(
        user_id=user_id, limit=2, cursor=page2.prev_cursor
    )
    assert len(page1_back.items) == 2
    assert page1_back.items[0].id == created_convs[4].id
    assert page1_back.items[1].id == created_convs[3].id
    assert page1_back.has_prev_page is False


@pytest.mark.asyncio
async def test_message_keyset_pagination_and_isolation(async_db):
    user_id = async_db.user_id
    conv_repo = SQLAlchemyConversationRepository(async_db)
    msg_repo = SQLAlchemyMessageRepository(async_db)

    now = datetime.now(UTC)
    conv_a = await conv_repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Conv A",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
    )

    conv_b = await conv_repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Conv B",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
    )

    # Add 4 messages to conv_a
    base_time = datetime.now(UTC) - timedelta(minutes=20)
    for i in range(4):
        await msg_repo.add_message(
            ConversationMessage(
                id=uuid4(),
                conversation_id=conv_a.id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"Message {i + 1}",
                status=MessageStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=i),
            )
        )

    # Page 1 for conv_a
    page1 = await msg_repo.list_messages(conversation_id=conv_a.id, limit=2)
    assert len(page1.items) == 2
    assert page1.has_next_page is True
    assert page1.next_cursor is not None

    # Verify that cursor generated for conv_a is rejected when attempted on conv_b
    with pytest.raises(InvalidCursorException, match="context mismatch"):
        await msg_repo.list_messages(
            conversation_id=conv_b.id, limit=2, cursor=page1.next_cursor
        )


@pytest.mark.asyncio
async def test_legacy_offset_rejection_conversations_api(async_db):
    user_id = async_db.user_id
    manager = ConversationManager(
        conversation_repo=SQLAlchemyConversationRepository(async_db),
        message_repo=SQLAlchemyMessageRepository(async_db),
        summary_repo=None,
        access_service=ConversationAccessService(
            SQLAlchemyConversationRepository(async_db)
        ),
        title_generator=None,
        memory=None,
        rewriter=None,
        event_dispatcher=None,
        db=async_db,
    )

    app.state.is_draining = False
    app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id)
    }
    app.dependency_overrides[get_conversation_manager] = lambda: manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Offset only -> Rejected with HTTP 400
        res_offset_only = await client.get("/api/v1/conversations?offset=10")
        assert res_offset_only.status_code == 400
        assert "Legacy offset pagination is not supported" in res_offset_only.text

        # 2. Cursor + Offset -> Rejected with HTTP 400
        res_cursor_offset = await client.get(
            "/api/v1/conversations?cursor=fake.token&offset=10"
        )
        assert res_cursor_offset.status_code == 400
        assert "Legacy offset pagination is not supported" in res_cursor_offset.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_legacy_offset_rejection_messages_api(async_db):
    user_id = async_db.user_id
    conv_repo = SQLAlchemyConversationRepository(async_db)
    msg_repo = SQLAlchemyMessageRepository(async_db)

    conv = await conv_repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Messages API Test",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_message_at=datetime.now(UTC),
        )
    )

    manager = ConversationManager(
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        summary_repo=None,
        access_service=ConversationAccessService(conv_repo),
        title_generator=None,
        memory=None,
        rewriter=None,
        event_dispatcher=None,
        db=async_db,
    )

    app.state.is_draining = False
    app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id)
    }
    app.dependency_overrides[get_conversation_manager] = lambda: manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Offset only -> Rejected with HTTP 400
        res_offset_only = await client.get(
            f"/api/v1/conversations/{conv.id}/messages?offset=10"
        )
        assert res_offset_only.status_code == 400
        assert "Legacy offset pagination is not supported" in res_offset_only.text

        # 2. Cursor + Offset -> Rejected with HTTP 400
        res_cursor_offset = await client.get(
            f"/api/v1/conversations/{conv.id}/messages?cursor=fake.token&offset=10"
        )
        assert res_cursor_offset.status_code == 400
        assert "Legacy offset pagination is not supported" in res_cursor_offset.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_e2e_conversations_api_cursor_traversal(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    now = datetime.now(UTC)
    for i in range(5):
        await repo.create_conversation(
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title=f"API Conv {i}",
                state=ConversationState.ACTIVE,
                settings=ConversationSettings(),
                metadata=ConversationMetadata(),
                created_at=now + timedelta(minutes=i),
                updated_at=now + timedelta(minutes=i),
                last_message_at=now + timedelta(minutes=i),
            )
        )

    manager = ConversationManager(
        conversation_repo=repo,
        message_repo=SQLAlchemyMessageRepository(async_db),
        summary_repo=None,
        access_service=ConversationAccessService(repo),
        title_generator=None,
        memory=None,
        rewriter=None,
        event_dispatcher=None,
        db=async_db,
    )

    app.state.is_draining = False
    app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id)
    }
    app.dependency_overrides[get_conversation_manager] = lambda: manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial page: no cursor
        res1 = await client.get("/api/v1/conversations?limit=2")
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1["items"]) == 2
        assert data1["has_next_page"] is True
        assert data1["next_cursor"] is not None
        assert "offset" not in data1 or data1.get("offset") is None

        # Next page: using next_cursor
        res2 = await client.get(
            f"/api/v1/conversations?limit=2&cursor={data1['next_cursor']}"
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert len(data2["items"]) == 2
        assert data2["has_next_page"] is True
        assert data2["next_cursor"] is not None

        # Disjoint page validation: no overlap in conversation IDs
        ids1 = {c["id"] for c in data1["items"]}
        for c in data2["items"]:
            assert c["id"] not in ids1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_offset_used_in_production_repositories():
    """Static verification: ensure no .offset() call exists in conversation/message repository query paths."""
    import inspect

    from app.chat.infrastructure.persistence.repositories import (
        conversation_repository,
        message_repository,
    )

    conv_source = inspect.getsource(
        conversation_repository.SQLAlchemyConversationRepository.list_conversations
    )
    msg_source = inspect.getsource(
        message_repository.SQLAlchemyMessageRepository.list_messages
    )
    msg_recent_source = inspect.getsource(
        message_repository.SQLAlchemyMessageRepository.get_recent_messages
    )

    assert ".offset(" not in conv_source, (
        "list_conversations contains forbidden .offset() call"
    )
    assert ".offset(" not in msg_source, (
        "list_messages contains forbidden .offset() call"
    )
    assert ".offset(" not in msg_recent_source, (
        "get_recent_messages contains forbidden .offset() call"
    )


@pytest.mark.asyncio
async def test_soft_deleted_conversations_filtered_out(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    now = datetime.now(UTC)
    active_conv = await repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Active Conv",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
    )

    await repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Deleted Conv",
            state=ConversationState.DELETED,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=now + timedelta(minutes=1),
            updated_at=now + timedelta(minutes=1),
            last_message_at=now + timedelta(minutes=1),
        )
    )

    page = await repo.list_conversations(user_id=user_id, limit=10)
    assert len(page.items) == 1
    assert page.items[0].id == active_conv.id


@pytest.mark.asyncio
async def test_identical_timestamps_tie_breaking_via_id(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    fixed_time = datetime.now(UTC)
    id1 = uuid4()
    id2 = uuid4()
    # Ensure id1 < id2 or sort them
    low_id, high_id = sorted([id1, id2])

    await repo.create_conversation(
        Conversation(
            id=low_id,
            user_id=user_id,
            title="Low UUID",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=fixed_time,
            updated_at=fixed_time,
            last_message_at=fixed_time,
        )
    )

    await repo.create_conversation(
        Conversation(
            id=high_id,
            user_id=user_id,
            title="High UUID",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=fixed_time,
            updated_at=fixed_time,
            last_message_at=fixed_time,
        )
    )

    # Page 1: limit=1 -> should return high_id first (DESC)
    page1 = await repo.list_conversations(user_id=user_id, limit=1)
    assert len(page1.items) == 1
    assert page1.items[0].id == high_id
    assert page1.has_next_page is True

    # Page 2: forward using next_cursor -> should return low_id
    page2 = await repo.list_conversations(
        user_id=user_id, limit=1, cursor=page1.next_cursor
    )
    assert len(page2.items) == 1
    assert page2.items[0].id == low_id
    assert page2.has_next_page is False


@pytest.mark.asyncio
async def test_empty_table_returns_empty_page_with_null_cursors(async_db):
    user_id = uuid4()
    repo = SQLAlchemyConversationRepository(async_db)

    page = await repo.list_conversations(user_id=user_id, limit=20)
    assert len(page.items) == 0
    assert page.next_cursor is None
    assert page.prev_cursor is None
    assert page.has_next_page is False
    assert page.has_prev_page is False


@pytest.mark.asyncio
async def test_invalid_cursor_returns_http_400(async_db):
    user_id = async_db.user_id
    manager = ConversationManager(
        conversation_repo=SQLAlchemyConversationRepository(async_db),
        message_repo=SQLAlchemyMessageRepository(async_db),
        summary_repo=None,
        access_service=ConversationAccessService(
            SQLAlchemyConversationRepository(async_db)
        ),
        title_generator=None,
        memory=None,
        rewriter=None,
        event_dispatcher=None,
        db=async_db,
    )

    app.state.is_draining = False
    app.dependency_overrides[get_current_user_context] = lambda: {
        "user_id": str(user_id)
    }
    app.dependency_overrides[get_conversation_manager] = lambda: manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/conversations?cursor=invalid_base64_token")
        assert response.status_code == 400
        assert "Malformed cursor" in response.text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_traversal_100_items_zero_duplicates_zero_missing(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    # Insert 125 conversations with distinct timestamps
    base_time = datetime.now(UTC) - timedelta(days=10)
    created_ids = []
    for i in range(125):
        conv = Conversation(
            id=uuid4(),
            user_id=user_id,
            title=f"Large Suite Conv {i}",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=base_time + timedelta(minutes=i),
            updated_at=base_time + timedelta(minutes=i),
            last_message_at=base_time + timedelta(minutes=i),
        )
        saved = await repo.create_conversation(conv)
        created_ids.append(saved.id)

    # Traverse all 125 items page-by-page (limit=20)
    collected_ids = []
    cursor = None
    page_count = 0

    while True:
        page = await repo.list_conversations(user_id=user_id, limit=20, cursor=cursor)
        page_count += 1
        for item in page.items:
            collected_ids.append(item.id)

        if not page.has_next_page or not page.next_cursor:
            break
        cursor = page.next_cursor

    # Invariants 1, 2, 3: Exactly 125 returned, 0 duplicates, 0 missing, ordered DESC
    assert len(collected_ids) == 125
    assert len(set(collected_ids)) == 125
    assert collected_ids == list(reversed(created_ids))
    assert page_count == 7  # 6 full pages of 20 + 1 page of 5


@pytest.mark.asyncio
async def test_concurrent_insertion_behavior_with_cursor(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    base_time = datetime.now(UTC) - timedelta(hours=5)
    for i in range(10):
        await repo.create_conversation(
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title=f"Conv {i}",
                state=ConversationState.ACTIVE,
                settings=ConversationSettings(),
                metadata=ConversationMetadata(),
                created_at=base_time + timedelta(minutes=i),
                updated_at=base_time + timedelta(minutes=i),
                last_message_at=base_time + timedelta(minutes=i),
            )
        )

    # Fetch page 1 (items 9, 8)
    page1 = await repo.list_conversations(user_id=user_id, limit=2)
    assert len(page1.items) == 2

    # Concurrently insert 5 NEW conversations with timestamps AFTER base_time + 10m
    new_time = base_time + timedelta(hours=1)
    for i in range(5):
        await repo.create_conversation(
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title=f"New Conv {i}",
                state=ConversationState.ACTIVE,
                settings=ConversationSettings(),
                metadata=ConversationMetadata(),
                created_at=new_time + timedelta(minutes=i),
                updated_at=new_time + timedelta(minutes=i),
                last_message_at=new_time + timedelta(minutes=i),
            )
        )

    # Invariant 7: Fetch page 2 using page1.next_cursor.
    # In offset pagination, inserting 5 new items would shift the offset and cause duplicate reads of items 9, 8!
    # In keyset pagination, page 2 MUST continue seamlessly to items 7, 6 without duplicates or skips.
    page2 = await repo.list_conversations(
        user_id=user_id, limit=2, cursor=page1.next_cursor
    )
    assert len(page2.items) == 2
    # Ensure neither of page 2's items were in page 1
    page1_ids = {item.id for item in page1.items}
    for item in page2.items:
        assert item.id not in page1_ids


@pytest.mark.asyncio
async def test_deletion_between_page_requests(async_db):
    user_id = async_db.user_id
    repo = SQLAlchemyConversationRepository(async_db)

    base_time = datetime.now(UTC) - timedelta(hours=2)
    convs = []
    for i in range(6):
        c = await repo.create_conversation(
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title=f"Conv {i}",
                state=ConversationState.ACTIVE,
                settings=ConversationSettings(),
                metadata=ConversationMetadata(),
                created_at=base_time + timedelta(minutes=i),
                updated_at=base_time + timedelta(minutes=i),
                last_message_at=base_time + timedelta(minutes=i),
            )
        )
        convs.append(c)

    # Page 1 (items 5, 4)
    page1 = await repo.list_conversations(user_id=user_id, limit=2)
    assert len(page1.items) == 2

    # Invariant 8: Soft-delete item 3 (the first item that would appear on Page 2)
    await repo.delete_conversation(convs[3].id)

    # Fetch Page 2: should seamlessly return items 2, 1 (skipping deleted item 3)
    page2 = await repo.list_conversations(
        user_id=user_id, limit=2, cursor=page1.next_cursor
    )
    assert len(page2.items) == 2
    assert page2.items[0].id == convs[2].id
    assert page2.items[1].id == convs[1].id


@pytest.mark.asyncio
async def test_message_keyset_traversal_100_items(async_db):
    user_id = async_db.user_id
    conv_repo = SQLAlchemyConversationRepository(async_db)
    msg_repo = SQLAlchemyMessageRepository(async_db)

    conv = await conv_repo.create_conversation(
        Conversation(
            id=uuid4(),
            user_id=user_id,
            title="Message Traversal Conv",
            state=ConversationState.ACTIVE,
            settings=ConversationSettings(),
            metadata=ConversationMetadata(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_message_at=datetime.now(UTC),
        )
    )

    base_time = datetime.now(UTC) - timedelta(days=5)
    created_msg_ids = []
    for i in range(110):
        msg = await msg_repo.add_message(
            ConversationMessage(
                id=uuid4(),
                conversation_id=conv.id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"Message content {i}",
                status=MessageStatus.COMPLETED,
                created_at=base_time + timedelta(minutes=i),
            )
        )
        created_msg_ids.append(msg.id)

    # Traverse all 110 messages (limit=25)
    collected_msg_ids = []
    cursor = None

    while True:
        page = await msg_repo.list_messages(
            conversation_id=conv.id, limit=25, cursor=cursor
        )
        for m in page.items:
            collected_msg_ids.append(m.id)

        if not page.has_next_page or not page.next_cursor:
            break
        cursor = page.next_cursor

    assert len(collected_msg_ids) == 110
    assert len(set(collected_msg_ids)) == 110
    assert collected_msg_ids == list(reversed(created_msg_ids))
