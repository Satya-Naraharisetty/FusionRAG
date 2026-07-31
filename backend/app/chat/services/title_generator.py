import logging

from app.chat.domain.interfaces import ConversationTitleGenerator, LLMProvider
from app.chat.domain.models import ChatMessage, ChatRole

logger = logging.getLogger(__name__)


class LLMConversationTitleGenerator(ConversationTitleGenerator):
    def __init__(self, llm_provider: LLMProvider, model: str) -> None:
        self._llm_provider = llm_provider
        self._model = model

    def _fallback_title(self, user_msg: str) -> str:
        trimmed = user_msg.strip()
        if len(trimmed) > 40:
            return trimmed[:37] + "..."
        return trimmed or "New Conversation"

    async def generate_title(self, first_user_message: str, assistant_answer: str | None = None) -> str:
        """
        Generate a concise title for a conversation based on the first turn (user + optional assistant).
        Falls back to a truncated version of the user query on errors.
        """
        if not first_user_message.strip():
            return "New Conversation"

        system_prompt = (
            "You are an assistant that generates short, descriptive, and catchy titles for chat conversations.\n"
            "Given the user's first query and the assistant's response, write a title that is:\n"
            "- Catchy and concise (maximum 6 words)\n"
            "- Focused on the core subject\n"
            "- Free of quotes, markdown, or prefix text (e.g., do NOT start with 'Title:')"
        )

        user_content = f"User: {first_user_message.strip()}\n"
        if assistant_answer:
            user_content += f"Assistant: {assistant_answer.strip()}\n"

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=system_prompt),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]

        try:
            title, _ = await self._llm_provider.generate(
                messages=messages,
                model=self._model,
                temperature=0.3,
                max_tokens=30,
            )
            title = title.strip()
            # Remove any wrapping double or single quotes
            if (title.startswith('"') and title.endswith('"')) or (title.startswith("'") and title.endswith("'")):
                title = title[1:-1].strip()
            # Remove trailing period if generated
            if title.endswith("."):
                title = title[:-1].strip()

            return title or self._fallback_title(first_user_message)

        except Exception as e:
            logger.warning(f"Failed to generate AI conversation title: {e}. Falling back to text slice.")
            return self._fallback_title(first_user_message)
class FallbackConversationTitleGenerator(ConversationTitleGenerator):
    """
    Fallback implementation that quickly produces a title without calling the LLM.
    """
    async def generate_title(self, first_user_message: str, assistant_answer: str | None = None) -> str:
        trimmed = first_user_message.strip()
        if len(trimmed) > 40:
            return trimmed[:37] + "..."
        return trimmed or "New Conversation"
