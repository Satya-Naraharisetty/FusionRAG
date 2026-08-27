from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.infrastructure.persistence.models import SQLAlchemyUser
from app.chat.domain.models import ChatRole
from app.chat.infrastructure.persistence.models import (
    ConversationMessageORM,
    ConversationORM,
    ConversationSummaryORM,
)
from app.core.queue.handlers import SummarizeConversationJobHandler
from app.core.queue.interfaces import Job


@pytest.mark.asyncio
async def test_duplicate_summarize_conversation_job_is_idempotent(
    real_db_session_factory,
):
    user_id = uuid4()
    conv_id = uuid4()
    msg1_id = uuid4()
    msg2_id = uuid4()
    msg3_id = uuid4()
    msg4_id = uuid4()

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"summ_user_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            ConversationORM(
                id=conv_id,
                user_id=user_id,
                title="Summarization Idempotency Test",
            )
        )
        session.add(
            ConversationMessageORM(
                id=msg1_id,
                conversation_id=conv_id,
                role=ChatRole.USER.value,
                content="Hello, what is hybrid search?",
            )
        )
        session.add(
            ConversationMessageORM(
                id=msg2_id,
                conversation_id=conv_id,
                role=ChatRole.ASSISTANT.value,
                content="Hybrid search combines dense vectors with sparse BM25 or PostgreSQL FTS.",
            )
        )
        session.add(
            ConversationMessageORM(
                id=msg3_id,
                conversation_id=conv_id,
                role=ChatRole.USER.value,
                content="How does reciprocal rank fusion help?",
            )
        )
        session.add(
            ConversationMessageORM(
                id=msg4_id,
                conversation_id=conv_id,
                role=ChatRole.ASSISTANT.value,
                content="RRF merges rankings from dense and sparse retrievers without score normalization issues.",
            )
        )
        await session.commit()

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=("Consolidated summary of hybrid RAG and RRF discussions.", 25)
    )

    handler = SummarizeConversationJobHandler(
        db_session_factory=real_db_session_factory,
        llm_provider=mock_llm,
        summary_trigger_messages=4,
        max_messages_per_context=2,
    )

    job = Job(
        task_type="SUMMARIZE_CONVERSATION",
        payload={"conversation_id": str(conv_id), "user_id": str(user_id)},
    )

    # 1. First execution
    res1 = await handler.handle(job)
    assert res1.success is True

    async with real_db_session_factory() as session:
        summaries_1 = (
            (
                await session.execute(
                    select(ConversationSummaryORM).where(
                        ConversationSummaryORM.conversation_id == conv_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(summaries_1) == 1
        summary_id = summaries_1[0].id
        summary_text = summaries_1[0].summary

    # 2. Duplicate execution of the same job (simulating retry / at-least-once replay)
    res2 = await handler.handle(job)
    assert res2.success is True

    async with real_db_session_factory() as session:
        summaries_2 = (
            (
                await session.execute(
                    select(ConversationSummaryORM).where(
                        ConversationSummaryORM.conversation_id == conv_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(summaries_2) == 1
        assert summaries_2[0].id == summary_id
        assert summaries_2[0].summary == summary_text


@pytest.mark.asyncio
async def test_summarize_conversation_below_threshold_is_skipped(
    real_db_session_factory,
):
    user_id = uuid4()
    conv_id = uuid4()

    async with real_db_session_factory() as session:
        session.add(
            SQLAlchemyUser(
                id=user_id,
                email=f"summ_thresh_{uuid4().hex[:8]}@example.com",
                hashed_password="hash",
                is_active=True,
            )
        )
        session.add(
            ConversationORM(
                id=conv_id,
                user_id=user_id,
                title="Threshold Check",
            )
        )
        session.add(
            ConversationMessageORM(
                id=uuid4(),
                conversation_id=conv_id,
                role=ChatRole.USER.value,
                content="Short single message",
            )
        )
        await session.commit()

    mock_llm = AsyncMock()
    handler = SummarizeConversationJobHandler(
        db_session_factory=real_db_session_factory,
        llm_provider=mock_llm,
        summary_trigger_messages=4,
        max_messages_per_context=2,
    )

    job = Job(
        task_type="SUMMARIZE_CONVERSATION",
        payload={"conversation_id": str(conv_id)},
    )

    res = await handler.handle(job)
    assert res.success is True
    assert res.details.get("status") == "skipped_count_below_threshold"

    async with real_db_session_factory() as session:
        summaries = (
            (
                await session.execute(
                    select(ConversationSummaryORM).where(
                        ConversationSummaryORM.conversation_id == conv_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(summaries) == 0
