from uuid import UUID

from app.chat.domain.interfaces import (
    ConversationMemory,
    MessageRepository,
    SummaryRepository,
)
from app.chat.domain.models import ConversationMessage, ConversationSummary


class RollingConversationMemory(ConversationMemory):
    def __init__(
        self,
        message_repo: MessageRepository,
        summary_repo: SummaryRepository,
        max_messages: int = 12,
    ) -> None:
        self._message_repo = message_repo
        self._summary_repo = summary_repo
        self._max_messages = max_messages

    async def load_memory(
        self, conversation_id: UUID
    ) -> tuple[list[ConversationMessage], ConversationSummary | None]:
        """
        Load active conversation memory: the latest summary (if any)
        and recent messages created after the summarized window.
        """
        # 1. Fetch latest summary
        summary = await self._summary_repo.latest_summary(conversation_id)

        # 2. Fetch recent messages
        # We fetch up to 100 messages to ensure we cross any summary boundary
        messages = await self._message_repo.get_recent_messages(
            conversation_id, limit=100
        )

        if summary:
            # Filter out messages that are covered by the summary
            covered_idx = -1
            for idx, msg in enumerate(messages):
                if msg.id == summary.covered_until_message_id:
                    covered_idx = idx
                    break

            if covered_idx != -1:
                messages = messages[covered_idx + 1 :]
            else:
                # Fallback to timestamp filtering if the exact message was not in the recent batch
                messages = [m for m in messages if m.created_at > summary.created_at]

        # 3. Cap to the maximum allowed active messages (slice from the end)
        recent_messages = messages[-self._max_messages :]

        return recent_messages, summary
