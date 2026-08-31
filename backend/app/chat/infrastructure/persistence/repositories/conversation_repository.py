from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.chat.domain.exceptions import ConversationConcurrentUpdateException
from app.chat.domain.interfaces import ConversationRepository
from app.chat.domain.models import (
    Conversation,
    ConversationMetadata,
    ConversationSettings,
    ConversationState,
)
from app.chat.infrastructure.persistence.models import ConversationORM
from app.core.pagination import CursorDirection, CursorPage, CursorSigner


class SQLAlchemyConversationRepository(ConversationRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _to_domain(self, orm: ConversationORM) -> Conversation:
        settings_data = orm.settings_json or {}
        metadata_data = orm.metadata_json or {}
        return Conversation(
            id=orm.id,
            user_id=orm.user_id,
            title=orm.title,
            state=ConversationState(orm.state),
            settings=ConversationSettings(**settings_data),
            version=orm.version,
            metadata=ConversationMetadata(**metadata_data),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            last_message_at=orm.last_message_at,
        )

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        orm = ConversationORM(
            id=conversation.id,
            user_id=conversation.user_id,
            title=conversation.title,
            state=conversation.state.value,
            settings_json=conversation.settings.model_dump(),
            version=conversation.version,
            metadata_json=conversation.metadata.model_dump(),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
        )
        self._db.add(orm)
        await self._db.flush()
        await self._db.refresh(orm)
        return self._to_domain(orm)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        result = await self._db.execute(
            select(ConversationORM).where(ConversationORM.id == conversation_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        return self._to_domain(orm)

    async def list_conversations(
        self,
        user_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CursorPage[Conversation]:
        base_where = [
            ConversationORM.user_id == user_id,
            ConversationORM.state != ConversationState.DELETED.value,
        ]

        if cursor:
            cursor_ts, cursor_id, direction = CursorSigner.parse_boundary(
                token=cursor,
                expected_resource_type="conv",
                expected_context_id=user_id,
            )

            if direction == CursorDirection.NEXT:
                stmt = (
                    select(ConversationORM)
                    .where(
                        *base_where,
                        tuple_(ConversationORM.last_message_at, ConversationORM.id)
                        < tuple_(literal(cursor_ts), literal(cursor_id)),
                    )
                    .order_by(
                        ConversationORM.last_message_at.desc(),
                        ConversationORM.id.desc(),
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
                        created_at=items_orm[-1].last_message_at,
                        record_id=items_orm[-1].id,
                        direction=CursorDirection.NEXT,
                        resource_type="conv",
                        context_id=user_id,
                    )
                    if has_next_page and items_orm
                    else None
                )
                prev_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[0].last_message_at,
                        record_id=items_orm[0].id,
                        direction=CursorDirection.PREV,
                        resource_type="conv",
                        context_id=user_id,
                    )
                    if items_orm
                    else None
                )

                return CursorPage[Conversation](
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
                    select(ConversationORM)
                    .where(
                        *base_where,
                        tuple_(ConversationORM.last_message_at, ConversationORM.id)
                        > tuple_(literal(cursor_ts), literal(cursor_id)),
                    )
                    .order_by(
                        ConversationORM.last_message_at.asc(),
                        ConversationORM.id.asc(),
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
                        created_at=items_orm[-1].last_message_at,
                        record_id=items_orm[-1].id,
                        direction=CursorDirection.NEXT,
                        resource_type="conv",
                        context_id=user_id,
                    )
                    if items_orm
                    else None
                )
                prev_cursor = (
                    CursorSigner.encode(
                        created_at=items_orm[0].last_message_at,
                        record_id=items_orm[0].id,
                        direction=CursorDirection.PREV,
                        resource_type="conv",
                        context_id=user_id,
                    )
                    if has_prev_page and items_orm
                    else None
                )

                return CursorPage[Conversation](
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
            select(ConversationORM)
            .where(*base_where)
            .order_by(
                ConversationORM.last_message_at.desc(),
                ConversationORM.id.desc(),
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
                created_at=items_orm[-1].last_message_at,
                record_id=items_orm[-1].id,
                direction=CursorDirection.NEXT,
                resource_type="conv",
                context_id=user_id,
            )
            if has_next_page and items_orm
            else None
        )

        return CursorPage[Conversation](
            items=items,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=None,
            has_next_page=has_next_page,
            has_prev_page=False,
            has_more=has_next_page,
        )

    async def update_conversation(self, conversation: Conversation) -> Conversation:
        result = await self._db.execute(
            select(ConversationORM).where(ConversationORM.id == conversation.id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            raise RuntimeError(f"Conversation {conversation.id} not found for update.")

        if conversation.version != orm.version:
            raise ConversationConcurrentUpdateException(
                f"Concurrent update conflict on conversation {conversation.id}. "
                f"Expected version {conversation.version}, database has version {orm.version}."
            )

        # Assign values
        orm.title = conversation.title
        orm.state = conversation.state.value
        orm.settings_json = conversation.settings.model_dump()
        orm.metadata_json = conversation.metadata.model_dump()
        orm.last_message_at = conversation.last_message_at
        orm.updated_at = datetime.now(UTC)
        orm.version = conversation.version

        try:
            await self._db.flush()
            await self._db.refresh(orm)
        except StaleDataError as e:
            raise ConversationConcurrentUpdateException(
                f"Concurrent update conflict on conversation {conversation.id}: {e}"
            )

        return self._to_domain(orm)

    async def delete_conversation(self, conversation_id: UUID) -> None:
        # Soft delete
        result = await self._db.execute(
            select(ConversationORM).where(ConversationORM.id == conversation_id)
        )
        orm = result.scalar_one_or_none()
        if orm:
            orm.state = ConversationState.DELETED.value
            orm.updated_at = datetime.now(UTC)
            await self._db.flush()
