from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.domain.exceptions import (
    UnauthorizedConversationAccessException,
)
from app.chat.domain.models import (
    Conversation,
    ConversationMessage,
    MessageRole,
    MessageStatus,
)
from app.chat.services.conversation_manager import ConversationManager


@pytest.mark.asyncio
async def test_conversation_manager_delete_messages_from_success():
    conv_id = uuid4()
    user_id = uuid4()
    msg_id = uuid4()

    mock_conv_repo = AsyncMock()
    mock_msg_repo = AsyncMock()
    mock_sum_repo = AsyncMock()
    mock_access_service = AsyncMock()
    mock_memory = AsyncMock()
    mock_rewriter = AsyncMock()
    mock_title_generator = AsyncMock()
    mock_dispatcher = MagicMock()
    mock_db = AsyncMock()

    now = datetime.now(UTC)
    conv = Conversation(
        id=conv_id,
        user_id=user_id,
        title="Test Conversation",
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )
    mock_conv_repo.get_conversation.return_value = conv
    mock_msg_repo.delete_messages_from.return_value = 3
    mock_msg_repo.count_messages.return_value = 2

    remaining_msg = ConversationMessage(
        id=uuid4(),
        conversation_id=conv_id,
        role=MessageRole.ASSISTANT,
        content="Remaining reply",
        status=MessageStatus.COMPLETED,
        created_at=datetime(2026, 8, 31, 0, 0, tzinfo=UTC),
    )
    mock_msg_repo.get_recent_messages.return_value = [remaining_msg]

    manager = ConversationManager(
        conversation_repo=mock_conv_repo,
        message_repo=mock_msg_repo,
        summary_repo=mock_sum_repo,
        access_service=mock_access_service,
        memory=mock_memory,
        rewriter=mock_rewriter,
        title_generator=mock_title_generator,
        event_dispatcher=mock_dispatcher,
        db=mock_db,
    )

    deleted_count = await manager.delete_messages_from(conv_id, user_id, msg_id)

    assert deleted_count == 3
    mock_access_service.verify_owner.assert_awaited_once_with(conv_id, user_id)
    mock_msg_repo.delete_messages_from.assert_awaited_once_with(
        conversation_id=conv_id, message_id=msg_id
    )
    assert conv.metadata.message_count == 2
    assert conv.last_message_at == remaining_msg.created_at
    mock_conv_repo.update_conversation.assert_awaited_once_with(conv)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_conversation_manager_delete_messages_from_unauthorized():
    conv_id = uuid4()
    user_id = uuid4()
    msg_id = uuid4()

    mock_access_service = AsyncMock()
    mock_access_service.verify_owner.side_effect = (
        UnauthorizedConversationAccessException("Forbidden")
    )

    manager = ConversationManager(
        conversation_repo=AsyncMock(),
        message_repo=AsyncMock(),
        summary_repo=AsyncMock(),
        access_service=mock_access_service,
        memory=AsyncMock(),
        rewriter=AsyncMock(),
        title_generator=AsyncMock(),
        event_dispatcher=MagicMock(),
    )

    with pytest.raises(UnauthorizedConversationAccessException):
        await manager.delete_messages_from(conv_id, user_id, msg_id)
