import uuid
from datetime import UTC, datetime
from uuid import UUID

from app.chat.domain.interfaces import (
    ConversationSummarizer,
    LLMProvider,
    MessageRepository,
    SummaryRepository,
)
from app.chat.domain.models import (
    ChatMessage,
    ChatRole,
    ConversationSummary,
)


class LLMConversationSummarizer(ConversationSummarizer):
    def __init__(
        self,
        llm_provider: LLMProvider,
        summary_repo: SummaryRepository,
        message_repo: MessageRepository,
        model: str,
        summary_max_tokens: int = 400,
    ) -> None:
        self._llm_provider = llm_provider
        self._summary_repo = summary_repo
        self._message_repo = message_repo
        self._model = model
        self._summary_max_tokens = summary_max_tokens

    async def summarize(
        self, conversation_id: UUID, up_to_message_id: UUID
    ) -> ConversationSummary:
        """
        Summarize conversation history up to a specific message ID.
        Fuses any existing summary with newer messages to create a versioned rolling summary.
        """
        # 1. Fetch messages for the conversation
        messages = await self._message_repo.get_recent_messages(
            conversation_id, limit=1000
        )
        # Reverse to get chronological order (ascending) if get_recent_messages returns descending
        # Wait, get_recent_messages in SQLAlchemyMessageRepository reverses and returns chronological!
        # So it is already in ascending order.
        target_idx = -1
        for idx, msg in enumerate(messages):
            if msg.id == up_to_message_id:
                target_idx = idx
                break

        if target_idx == -1:
            raise RuntimeError(
                f"Message {up_to_message_id} was not found in conversation history."
            )

        # Slices from beginning up to the target message
        messages_to_summarize = messages[: target_idx + 1]
        if not messages_to_summarize:
            raise RuntimeError("No messages found to summarize.")

        # 2. Fetch the latest summary
        prev_summary = await self._summary_repo.latest_summary(conversation_id)

        # Filter messages to summarize to only include those after the previous summary
        if prev_summary:
            prev_covered_idx = -1
            for idx, msg in enumerate(messages_to_summarize):
                if msg.id == prev_summary.covered_until_message_id:
                    prev_covered_idx = idx
                    break

            if prev_covered_idx != -1:
                new_messages_only = messages_to_summarize[prev_covered_idx + 1 :]
            else:
                new_messages_only = [
                    m
                    for m in messages_to_summarize
                    if m.created_at > prev_summary.created_at
                ]
        else:
            new_messages_only = messages_to_summarize

        # If there are no new messages to summarize, just return the previous summary (or mock one if somehow empty)
        if not new_messages_only and prev_summary:
            return prev_summary

        # 3. Formulate prompts
        if prev_summary:
            system_prompt = (
                f"You are a precise AI assistant. Your task is to update a conversation summary with new messages.\n"
                f"Consolidate the existing summary and the new messages into a single, cohesive rolling summary.\n"
                f"Focus on facts, questions asked, and answers retrieved. Keep the summary under {self._summary_max_tokens} tokens."
            )
            user_content_parts = [
                f"Existing Summary:\n{prev_summary.summary}\n\n",
                "New Messages:\n",
            ]
            for m in new_messages_only:
                user_content_parts.append(f"{m.role.value.capitalize()}: {m.content}\n")
            user_content = "".join(user_content_parts)
        else:
            system_prompt = (
                f"You are a precise AI assistant. Your task is to write a concise summary of the conversation history.\n"
                f"Focus on facts, questions asked, and answers retrieved. Keep the summary under {self._summary_max_tokens} tokens."
            )
            user_content_parts = ["Messages to summarize:\n"]
            for m in new_messages_only:
                user_content_parts.append(f"{m.role.value.capitalize()}: {m.content}\n")
            user_content = "".join(user_content_parts)

        # 4. Generate summary
        messages_payload = [
            ChatMessage(role=ChatRole.SYSTEM, content=system_prompt),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]

        summary_text, _ = await self._llm_provider.generate(
            messages=messages_payload,
            model=self._model,
            temperature=0.0,
            max_tokens=self._summary_max_tokens,
        )
        summary_text = summary_text.strip()

        # 5. Build and save the ConversationSummary model
        new_summary = ConversationSummary(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            summary=summary_text,
            summary_version=(prev_summary.summary_version + 1) if prev_summary else 1,
            covered_from_message_id=prev_summary.covered_from_message_id
            if prev_summary
            else messages_to_summarize[0].id,
            covered_until_message_id=up_to_message_id,
            message_count=len(messages_to_summarize),
            created_at=datetime.now(UTC),
        )

        return await self._summary_repo.save_summary(new_summary)
