from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
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


class SQLAlchemyConversationRepository(ConversationRepository):
    def __init__(self, db: Session) -> None:
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
        self._db.flush()
        return self._to_domain(orm)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        orm = (
            self._db.query(ConversationORM)
            .filter(ConversationORM.id == conversation_id)
            .first()
        )
        if not orm:
            return None
        return self._to_domain(orm)

    async def list_conversations(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[Conversation]:
        orms = (
            self._db.query(ConversationORM)
            .filter(
                ConversationORM.user_id == user_id,
                ConversationORM.state != ConversationState.DELETED.value,
            )
            .order_by(ConversationORM.last_message_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [self._to_domain(orm) for orm in orms]

    async def update_conversation(self, conversation: Conversation) -> Conversation:
        orm = (
            self._db.query(ConversationORM)
            .filter(ConversationORM.id == conversation.id)
            .first()
        )
        if not orm:
            # We can create it if not exists, but typically it should exist
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
        orm.updated_at = datetime.utcnow()
        orm.version = conversation.version

        try:
            self._db.flush()
        except StaleDataError as e:
            raise ConversationConcurrentUpdateException(
                f"Concurrent update conflict on conversation {conversation.id}: {e}"
            )

        return self._to_domain(orm)

    async def delete_conversation(self, conversation_id: UUID) -> None:
        # Soft delete
        orm = (
            self._db.query(ConversationORM)
            .filter(ConversationORM.id == conversation_id)
            .first()
        )
        if orm:
            orm.state = ConversationState.DELETED.value
            orm.updated_at = datetime.utcnow()
            self._db.flush()
