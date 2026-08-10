from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.chat.domain.interfaces import MessageRepository
from app.chat.domain.models import (
    ConversationMessage,
    MessageRole,
    MessageStatus,
)
from app.chat.infrastructure.persistence.models import ConversationMessageORM


class SQLAlchemyMessageRepository(MessageRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    async def _next_created_at(
        self, conversation_id: UUID, proposed: datetime | None = None
    ) -> datetime:
        """
        Returns a strictly increasing timestamp for the conversation.

        Messages created within the same microsecond would otherwise tie on
        created_at, making their relative order ambiguous (and the message
        history ordering nondeterministic). Bump the timestamp forward when it
        does not strictly exceed the newest existing message.
        """
        if proposed is None:
            proposed = datetime.now(UTC)
        latest = (
            self._db.query(func.max(ConversationMessageORM.created_at))
            .filter(ConversationMessageORM.conversation_id == conversation_id)
            .scalar()
        )
        if latest is not None and proposed <= latest:
            proposed = latest + timedelta(microseconds=1)
        return proposed

    def _to_domain(self, orm: ConversationMessageORM) -> ConversationMessage:
        return ConversationMessage(
            id=orm.id,
            conversation_id=orm.conversation_id,
            role=MessageRole(orm.role),
            content=orm.content,
            status=MessageStatus(orm.status),
            citations=orm.citations,
            prompt_tokens=orm.prompt_tokens,
            completion_tokens=orm.completion_tokens,
            tool_calls=orm.tool_calls,
            metadata=orm.metadata_json,
            attachments=orm.attachments,
            structured_content=orm.structured_content,
            created_at=orm.created_at,
        )

    async def add_message(self, message: ConversationMessage) -> ConversationMessage:
        created_at = await self._next_created_at(
            message.conversation_id, message.created_at
        )
        orm = ConversationMessageORM(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role.value,
            content=message.content,
            status=message.status.value,
            citations=message.citations,
            prompt_tokens=message.prompt_tokens,
            completion_tokens=message.completion_tokens,
            tool_calls=message.tool_calls,
            metadata_json=message.metadata,
            attachments=message.attachments,
            structured_content=message.structured_content,
            created_at=created_at,
        )
        self._db.add(orm)
        self._db.flush()
        return self._to_domain(orm)

    async def get_recent_messages(
        self, conversation_id: UUID, limit: int, offset: int = 0
    ) -> list[ConversationMessage]:
        orms = (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.conversation_id == conversation_id)
            # Secondary sort on id keeps ordering deterministic when created_at
            # timestamps tie (messages created within the same microsecond).
            .order_by(
                ConversationMessageORM.created_at.desc(),
                ConversationMessageORM.id.desc(),
            )
            .limit(limit)
            .offset(offset)
            .all()
        )
        # We fetch in descending order, but let's reverse them so they are in chronological order
        result = [self._to_domain(orm) for orm in orms]
        result.reverse()
        return result

    async def count_messages(self, conversation_id: UUID) -> int:
        return (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.conversation_id == conversation_id)
            .count()
        )

    async def create_assistant_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        role: MessageRole,
        content: str = "",
    ) -> ConversationMessage:
        created_at = await self._next_created_at(conversation_id)
        orm = ConversationMessageORM(
            id=message_id,
            conversation_id=conversation_id,
            role=role.value,
            content=content,
            status=MessageStatus.PENDING.value,
            created_at=created_at,
        )
        self._db.add(orm)
        self._db.flush()
        return self._to_domain(orm)

    async def append_stream_chunk(self, message_id: UUID, content_chunk: str) -> None:
        orm = (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.id == message_id)
            .first()
        )
        if orm:
            from app.chat.domain.exceptions import InvalidStatusTransitionException

            if orm.status not in (
                MessageStatus.PENDING.value,
                MessageStatus.STREAMING.value,
            ):
                raise InvalidStatusTransitionException(
                    f"Cannot transition message {message_id} from {orm.status} to STREAMING"
                )
            orm.content = (orm.content or "") + content_chunk
            orm.status = MessageStatus.STREAMING.value
            self._db.flush()

    async def complete_message(
        self,
        message_id: UUID,
        prompt_tokens: int,
        completion_tokens: int,
        citations: list[dict[str, Any]] | None = None,
        content: str | None = None,
    ) -> ConversationMessage:
        orm = (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.id == message_id)
            .first()
        )
        if not orm:
            raise RuntimeError(f"Message {message_id} not found to complete.")

        from app.chat.domain.exceptions import InvalidStatusTransitionException

        if orm.status not in (
            MessageStatus.PENDING.value,
            MessageStatus.STREAMING.value,
        ):
            raise InvalidStatusTransitionException(
                f"Cannot transition message {message_id} from {orm.status} to COMPLETED"
            )

        if content is not None:
            orm.content = content
        orm.prompt_tokens = prompt_tokens
        orm.completion_tokens = completion_tokens
        orm.citations = citations
        orm.status = MessageStatus.COMPLETED.value
        self._db.flush()
        return self._to_domain(orm)

    async def fail_message(
        self, message_id: UUID, error_message: str | None = None
    ) -> ConversationMessage:
        orm = (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.id == message_id)
            .first()
        )
        if not orm:
            raise RuntimeError(f"Message {message_id} not found to fail.")

        from app.chat.domain.exceptions import InvalidStatusTransitionException

        if orm.status not in (
            MessageStatus.PENDING.value,
            MessageStatus.STREAMING.value,
        ):
            raise InvalidStatusTransitionException(
                f"Cannot transition message {message_id} from {orm.status} to FAILED"
            )

        orm.status = MessageStatus.FAILED.value
        if error_message:
            meta = orm.metadata_json or {}
            meta["error_message"] = error_message
            orm.metadata_json = meta

        self._db.flush()
        return self._to_domain(orm)

    async def interrupt_message(
        self, message_id: UUID, reason: str | None = None
    ) -> ConversationMessage:
        """
        Transition a PENDING/STREAMING message to INTERRUPTED, preserving any
        partial content already streamed.

        Idempotent: messages already in a terminal status (COMPLETED, FAILED,
        INTERRUPTED) are returned unchanged so this can be used as a safety
        sweep after abnormal stream termination without racing the normal
        finalize/fail path.
        """
        orm = (
            self._db.query(ConversationMessageORM)
            .filter(ConversationMessageORM.id == message_id)
            .first()
        )
        if not orm:
            raise RuntimeError(f"Message {message_id} not found to interrupt.")

        if orm.status not in (
            MessageStatus.PENDING.value,
            MessageStatus.STREAMING.value,
        ):
            return self._to_domain(orm)

        orm.status = MessageStatus.INTERRUPTED.value
        if reason:
            meta = orm.metadata_json or {}
            meta["interrupt_reason"] = reason
            orm.metadata_json = meta

        self._db.flush()
        return self._to_domain(orm)
