import hashlib
import logging
from uuid import UUID

from app.chat.domain.interfaces import HistoryRewriteCache, HistoryRewriter, LLMProvider
from app.chat.domain.models import (
    ChatMessage,
    ChatRole,
    ConversationMessage,
    HistoryRewriteResult,
    MessageRole,
)

logger = logging.getLogger(__name__)


class LLMHistoryRewriter(HistoryRewriter):
    def __init__(
        self,
        llm_provider: LLMProvider,
        model: str,
        cache: HistoryRewriteCache,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._llm_provider = llm_provider
        self._model = model
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds

        self._system_prompt = (
            "You are an expert query rewriter. Given a conversation history and a follow-up question, "
            "rewrite the follow-up question into a single standalone question that contains all "
            "necessary context from the history. It must be understandable without the conversation history.\n"
            "Rules:\n"
            "1. Do NOT answer the question. Only return the rewritten question.\n"
            "2. If the question does not refer to the conversation history, return the original question exactly as-is.\n"
            "3. Keep the tone and intent of the original question."
        )

    def _get_cache_key(
        self, conversation_id: UUID, last_message_id: UUID, question: str
    ) -> str:
        q_hash = hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()
        return f"rewrite:{conversation_id}:{last_message_id}:{q_hash}"

    def _heuristically_needs_rewrite(self, question: str) -> bool:
        """
        Determine if the question relies on context.
        If it uses pronouns or context indicators, it needs rewriting.
        """
        # Lowercase for comparison
        q_lower = question.lower().strip()

        # Pronouns and contextual keywords
        pronouns = {
            "it",
            "its",
            "they",
            "them",
            "their",
            "he",
            "him",
            "his",
            "she",
            "her",
            "hers",
            "this",
            "that",
            "these",
            "those",
            "then",
            "there",
            "here",
            "himself",
            "herself",
            "former",
            "latter",
            "whom",
            "whose",
            "which",
        }
        words = set(q_lower.translate(str.maketrans("", "", "?.,!/")).split())

        # If any pronoun matches, it likely needs rewrite
        if not words.isdisjoint(pronouns):
            return True

        # Check for conversational follow-ups
        follow_up_phrases = [
            "about",
            "more",
            "explain",
            "why",
            "how",
            "what about",
            "tell me",
            "what was",
            "who was",
            "where was",
        ]
        for phrase in follow_up_phrases:
            if phrase in q_lower:
                return True

        # Extremely short queries (e.g. 1-2 words) are context-dependent
        if len(words) <= 2:
            return True

        return False

    async def rewrite(
        self, question: str, history: list[ConversationMessage]
    ) -> HistoryRewriteResult:
        """
        Rewrite follow-up question to standalone form based on conversational context.
        Uses cached responses to minimize latency and LLM cost.
        """
        # 1. Bypass if no history
        if not history:
            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="No conversation history available.",
                rewrite_applied=False,
            )

        # 2. Check Cache
        last_message = history[-1]
        cache_key = self._get_cache_key(
            last_message.conversation_id, last_message.id, question
        )

        try:
            cached_val = await self._cache.get(cache_key)
            if cached_val:
                logger.info(f"Query rewrite cache hit for key: {cache_key}")
                return HistoryRewriteResult(
                    original_query=question,
                    rewritten_query=cached_val,
                    rewrite_reason="Cache hit",
                    rewrite_applied=True,
                )
        except Exception as e:
            logger.warning(f"Failed to read from rewrite cache: {e}")

        # 4. Generate standalone question via LLM
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=self._system_prompt)]
        # Include last 6 messages to keep context concise
        for msg in history[-6:]:
            messages.append(
                ChatMessage(
                    role=ChatRole.USER
                    if msg.role == MessageRole.USER
                    else ChatRole.ASSISTANT,
                    content=msg.content,
                )
            )

        # Add current follow-up
        messages.append(
            ChatMessage(role=ChatRole.USER, content=f"Follow-up question: {question}")
        )

        try:
            rewritten_text, _ = await self._llm_provider.generate(
                messages=messages,
                model=self._model,
                temperature=0.0,
                max_tokens=256,
            )
            rewritten_text = rewritten_text.strip()
            # Clean possible markdown wrap or quotes
            if rewritten_text.startswith('"') and rewritten_text.endswith('"'):
                rewritten_text = rewritten_text[1:-1].strip()

            # 5. Populate Cache
            try:
                await self._cache.set(cache_key, rewritten_text, self._cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to write to rewrite cache: {e}")

            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=rewritten_text,
                rewrite_reason="LLM rewriting applied successfully.",
                rewrite_applied=True,
            )

        except Exception as e:
            logger.exception(
                f"Error during query rewriting: {e}. Falling back to original question."
            )
            return HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason=f"Failed to generate rewrite due to LLM provider error: {e}",
                rewrite_applied=False,
            )
