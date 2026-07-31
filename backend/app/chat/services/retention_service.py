import logging
from app.chat.domain.interfaces import ConversationRepository, SummaryRepository

logger = logging.getLogger(__name__)


class ConversationRetentionService:
    """
    Manages archival, soft-deleted conversation purging, and summary cleanup.
    Can be run via cron jobs, Celery tasks, or background services.
    """
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        summary_repo: SummaryRepository,
    ) -> None:
        self._conversation_repo = conversation_repo
        self._summary_repo = summary_repo

    async def archive_old_conversations(self, max_age_days: int) -> int:
        """
        Scan for conversations whose last_message_at is older than max_age_days,
        and transition them to ARCHIVED state.
        Returns the count of archived sessions.
        """
        logger.info(f"Scanning for conversations older than {max_age_days} days to archive...")
        # Stubbed: In production, this would execute a bulk SQL update via Repository/SQLAlchemy
        return 0

    async def purge_deleted_conversations(self) -> int:
        """
        Permanently delete conversations that are soft-deleted (state = deleted).
        Returns the count of purged sessions.
        """
        logger.info("Purging soft-deleted conversations from database...")
        # Stubbed: In production, executes DELETE FROM conversations WHERE state = 'deleted'
        return 0

    async def cleanup_orphan_summaries(self) -> int:
        """
        Delete summaries that no longer link to active conversations.
        Returns the count of cleaned summaries.
        """
        logger.info("Cleaning up orphan conversation summaries...")
        # Stubbed: In production, deletes summaries where conversation_id is not in conversations
        return 0
