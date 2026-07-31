import logging
import os
from app.chat.domain.models import ChatMessage, ChatRole

logger = logging.getLogger(__name__)


class PromptBuilder:
    def __init__(self, system_prompt_path: str) -> None:
        self.system_prompt_path = system_prompt_path
        self._default_system_prompt = (
            "You are a helpful and precise AI assistant. Answer the user's question using ONLY the provided context.\n"
            "If the information is not present in the context, say \"I cannot answer this question based on the provided context.\"\n"
            "Do not invent any facts, make assumptions, or extrapolate beyond the provided text. Support every statement with citations to the source chunks (e.g. [Chunk 1], [Chunk 2])."
        )
        self._default_user_template = (
            "Context:\n{context}\n\n"
            "Question: {question}\n\n"
            "Answer:"
        )
        # Load and cache system prompt at initialization
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        if self.system_prompt_path and os.path.exists(self.system_prompt_path):
            try:
                with open(self.system_prompt_path, encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    logger.info(f"Loaded system prompt from {self.system_prompt_path}")
                    return content
            except Exception as e:
                logger.error(f"Failed to read system prompt file at {self.system_prompt_path}: {e}")
        logger.warning("Using default system prompt fallback.")
        return self._default_system_prompt

    def get_system_prompt(self) -> str:
        return self._system_prompt

    def build_messages(self, question: str, context: str) -> list[ChatMessage]:
        """
        Assemble the chat messages list (system message + user message).
        """
        user_content = self._default_user_template.format(
            context=context, question=question
        )
        return [
            ChatMessage(role=ChatRole.SYSTEM, content=self._system_prompt),
            ChatMessage(role=ChatRole.USER, content=user_content),
        ]
