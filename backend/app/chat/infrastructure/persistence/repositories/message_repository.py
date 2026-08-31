from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.domain.interfaces import MessageRepository
from app.chat.domain.models import (
    ConversationMessage,
    MessageRole,
    MessageStatus,
)
from app.chat.infrastructure.persistence.models import ConversationMessageORM
from app.core.pagination import CursorDirection, CursorPage, CursorSigner


class SQLAlchemyMessageRepository(MessageRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _next_created_at(
        self, conversation_id: UUID, proposed: datetime | None = None
    ) -> datetime:
        """
        Returns a strictly increasing timestamp for the conversation.
        Guarantees that each message has a unique and monotonic created_at
        so that ordering is strictly deterministic without depending on ID ties.
        """
        now = datetime.now(UTC)
        base = proposed if proposed is not None else now
        result = await self._db.execute(
            select(func.max(ConversationMessageORM.created_at)).where(
                ConversationMessageORM.conversation_id == conversation_id
            )
        )
        max_existing = result.scalar_one_or_none()
        if max_existing is None:
            return base
        if base <= max_existing:
            return max_existing + timedelta(microseconds=1)
        return base

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
        await self._db.flush()
        await self._db.refresh(orm)
        return self._to_domain(orm)

    async def get_recent_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[ConversationMessage]:
        result = await self._db.execute(
            select(ConversationMessageORM)
            .where(ConversationMessageORM.conversation_id == conversation_id)
            .order_by(
                ConversationMessageORM.created_at.desc(),
                ConversationMessageORM.id.desc(),
            )
            .limit(limit)
        )
        orms = list(result.scalars().all())
        result_list = [self._to_domain(orm) for orm in orms]
        result_list.reverse()
        return result_list

    async def list_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[ConversationMessage]:
        base_where = [ConversationMessageORM.conversation_id == conversation_id]

        if cursor:
            cursor_ts, cursor_id, direction = CursorSigner.parse_boundary(
                token=cursor,
                expected_resource_type="msg",
                expected_context_id=conversation_id,
            )

            if direction == CursorDirection.NEXT:
                stmt = (
                    select(ConversationMessageORM)
                    .where(
                        *base_where,
                        tuple_(
                            ConversationMessageORM.created_at, ConversationMessageORM.id
                        )
                        < tuple_(literal(cursor_ts), literal(cursor_id)),
                    )
                    .order_by(
                        ConversationMessageORM.created_at.desc(),
                        ConversationMessageORM.id.desc(),
                    )
                    .limit(limit + 1)
                )
                result = await self._db.execute(stmt)
                orms = list(result.scalars().all())
                has_next_page = len(orms) > limit
                items_orm = orms[:limit]
                items = [self._to_domain(o) for o in items_orm]

                next_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[-1].created_at,
                        record_id=items_orm[-1].id,
                        direction=CursorDirection.NEXT,
                        resource_type="msg",
                        context_id=conversation_id,
                    )
                    if has_next_page and items_orm
                    else None
                )
                prev_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[0].created_at,
                        record_id=items_orm[0].id,
                        direction=CursorDirection.PREV,
                        resource_type="msg",
                        context_id=conversation_id,
                    )
                    if items_orm
                    else None
                )

                return CursorPage[ConversationMessage](
                    items=items,
                    limit=limit,
                    next_cursor=next_cursor,
                    prev_cursor=prev_cursor,
                    has_next_page=has_next_page,
                    has_prev_page=True,
                    has_more=has_next_page,
                )

            else:  # CursorDirection.PREV
                stmt = (
                    select(ConversationMessageORM)
                    .where(
                        *base_where,
                        tuple_(
                            ConversationMessageORM.created_at, ConversationMessageORM.id
                        )
                        > tuple_(literal(cursor_ts), literal(cursor_id)),
                    )
                    .order_by(
                        ConversationMessageORM.created_at.asc(),
                        ConversationMessageORM.id.asc(),
                    )
                    .limit(limit + 1)
                )
                result = await self._db.execute(stmt)
                orms = list(result.scalars().all())
                has_prev_page = len(orms) > limit
                items_orm = orms[:limit]
                # Reorder ASC slice back to canonical DESC order
                items_orm.reverse()
                items = [self._to_domain(o) for o in items_orm]

                next_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[-1].created_at,
                        record_id=items_orm[-1].id,
                        direction=CursorDirection.NEXT,
                        resource_type="msg",
                        context_id=conversation_id,
                    )
                    if items_orm
                    else None
                )
                prev_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[0].created_at,
                        record_id=items_orm[0].id,
                        direction=CursorDirection.PREV,
                        resource_type="msg",
                        context_id=conversation_id,
                    )
                    if has_prev_page and items_orm
                    else None
                )

                return CursorPage[ConversationMessage](
                    items=items,
                    limit=limit,
                    next_cursor=next_cursor,
                    prev_cursor=prev_cursor,
                    has_next_page=True,
                    has_prev_page=has_prev_page,
                    has_more=True,
                )

        # Canonical first page
        stmt = (
            select(ConversationMessageORM)
            .where(*base_where)
            .order_by(
                ConversationMessageORM.created_at.desc(),
                ConversationMessageORM.id.desc(),
            )
            .limit(limit + 1)
        )
        result = await self._db.execute(stmt)
        orms = list(result.scalars().all())
        has_next_page = len(orms) > limit
        items_orm = orms[:limit]
        items = [self._to_domain(o) for o in items_orm]

        next_cursor = (
            CursorSigner.encode(
                created_at=items_orm[-1].created_at,
                record_id=items_orm[-1].id,
                direction=CursorDirection.NEXT,
                resource_type="msg",
                context_id=conversation_id,
            )
            if has_next_page and items_orm
            else None
        )

        return CursorPage[ConversationMessage](
            items=items,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=None,
            has_next_page=has_next_page,
            has_prev_page=False,
            has_more=has_next_page,
        )

    async def count_messages(self, conversation_id: UUID) -> int:
        result = await self._db.execute(
            select(func.count(ConversationMessageORM.id)).where(
                ConversationMessageORM.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

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
        await self._db.flush()
        await self._db.refresh(orm)
        return self._to_domain(orm)

    async def append_stream_chunk(self, message_id: UUID, content_chunk: str) -> None:
        result = await self._db.execute(
            select(ConversationMessageORM).where(
                ConversationMessageORM.id == message_id
            )
        )
        orm = result.scalar_one_or_none()
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
            await self._db.flush()

    async def complete_message(
        self,
        message_id: UUID,
        prompt_tokens: int,
        completion_tokens: int,
        citations: list[dict[str, Any]] | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        result = await self._db.execute(
            select(ConversationMessageORM).where(
                ConversationMessageORM.id == message_id
            )
        )
        orm = result.scalar_one_or_none()
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
        if metadata:
            current_meta = orm.metadata_json or {}
            # Ensure it is a dictionary we can update
            if isinstance(current_meta, dict):
                current_meta.update(metadata)
                orm.metadata_json = current_meta
        orm.status = MessageStatus.COMPLETED.value
        await self._db.flush()
        await self._db.refresh(orm)
        return self._to_domain(orm)

    async def fail_message(
        self, message_id: UUID, error_message: str | None = None
    ) -> ConversationMessage:
        result = await self._db.execute(
            select(ConversationMessageORM).where(
                ConversationMessageORM.id == message_id
            )
        )
        orm = result.scalar_one_or_none()
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

        await self._db.flush()
        await self._db.refresh(orm)
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
        result = await self._db.execute(
            select(ConversationMessageORM).where(
                ConversationMessageORM.id == message_id
            )
        )
        orm = result.scalar_one_or_none()
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

        await self._db.flush()
        await self._db.refresh(orm)
        return self._to_domain(orm)

    async def delete_messages_from(
        self, conversation_id: UUID, message_id: UUID
    ) -> int:
        """
        Delete the message with message_id and all messages created at or after it
        in the specified conversation. Returns the count of deleted messages.
        """
        result = await self._db.execute(
            select(ConversationMessageORM).where(
                ConversationMessageORM.id == message_id,
                ConversationMessageORM.conversation_id == conversation_id,
            )
        )
        target_orm = result.scalar_one_or_none()
        if not target_orm:
            return 0

        target_created_at = target_orm.created_at

        delete_stmt = delete(ConversationMessageORM).where(
            ConversationMessageORM.conversation_id == conversation_id,
            ConversationMessageORM.created_at >= target_created_at,
        )
        del_result = await self._db.execute(delete_stmt)
        await self._db.flush()
        return int(getattr(del_result, "rowcount", 0) or 0)
