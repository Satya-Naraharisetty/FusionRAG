from uuid import UUID

from app.chat.domain.interfaces import SummaryRepository
from app.chat.domain.models import ConversationSummary
from app.chat.infrastructure.persistence.models import ConversationSummaryORM
from sqlalchemy.orm import Session


class SQLAlchemySummaryRepository(SummaryRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def _to_domain(self, orm: ConversationSummaryORM) -> ConversationSummary:
        return ConversationSummary(
            id=orm.id,
            conversation_id=orm.conversation_id,
            summary=orm.summary,
            summary_version=orm.summary_version,
            covered_from_message_id=orm.covered_from_message_id,
            covered_until_message_id=orm.covered_until_message_id,
            message_count=orm.message_count,
            created_at=orm.created_at,
        )

    async def save_summary(self, summary: ConversationSummary) -> ConversationSummary:
        orm = ConversationSummaryORM(
            id=summary.id,
            conversation_id=summary.conversation_id,
            summary=summary.summary,
            summary_version=summary.summary_version,
            covered_from_message_id=summary.covered_from_message_id,
            covered_until_message_id=summary.covered_until_message_id,
            message_count=summary.message_count,
            created_at=summary.created_at,
        )
        self._db.add(orm)
        self._db.flush()
        return self._to_domain(orm)

    async def latest_summary(self, conversation_id: UUID) -> ConversationSummary | None:
        orm = (
            self._db.query(ConversationSummaryORM)
            .filter(ConversationSummaryORM.conversation_id == conversation_id)
            .order_by(ConversationSummaryORM.summary_version.desc())
            .first()
        )
        if not orm:
            return None
        return self._to_domain(orm)
