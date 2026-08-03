import logging
import os
from typing import Any
from app.chat.domain.models import ChatMessage, ChatRole
from app.documents.domain.models import RetrievedChunk

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

    def build_prompt(
        self,
        context_obj: Any,
        question: str,
        token_estimator: Any,
        max_context_tokens: int,
        max_memory_tokens: int = 3000,
    ) -> tuple[list[ChatMessage], list[RetrievedChunk]]:
        """
        Assemble and budget the final chat messages list.
        Enforces explicit budget priorities:
        1. System Prompt (including rolling summaries)
        2. Current Question baseline
        3. History messages (within MAX_MEMORY_TOKENS & remaining budget)
        4. Retrieved document context (from remaining budget)
        """
        from app.chat.domain.models import ChatMessage, ChatRole, MessageRole

        # 1. System Prompt & Summaries
        system_content = self._system_prompt
        if context_obj.summary:
            system_content += f"\n\nConversation Summary:\n{context_obj.summary.summary}"
        
        system_tokens = token_estimator.estimate(system_content)

        # 2. Current Question baseline (without document context)
        baseline_question = f"Context:\n\n\nQuestion: {question}\n\nAnswer:"
        baseline_tokens = token_estimator.estimate(baseline_question)

        # Remaining budget for History & Chunks
        remaining_budget = max_context_tokens - system_tokens - baseline_tokens
        if remaining_budget < 0:
            # Under extreme budget constraints, fallback to system prompt & question only
            remaining_budget = 0

        # 3. Add history messages (User/Assistant turns) from newest to oldest
        history_messages: list[ChatMessage] = []
        accumulated_history_tokens = 0

        # Loop backwards through recent messages
        for msg in reversed(context_obj.recent_messages):
            msg_tokens = token_estimator.estimate(msg.content)
            # Check budgets
            if accumulated_history_tokens + msg_tokens > max_memory_tokens:
                break
            if accumulated_history_tokens + msg_tokens > remaining_budget:
                break

            role_map = ChatRole.USER if msg.role == MessageRole.USER else ChatRole.ASSISTANT
            history_messages.append(ChatMessage(role=role_map, content=msg.content))
            accumulated_history_tokens += msg_tokens

        # Restore chronological order of history messages
        history_messages.reverse()

        # Update remaining budget for chunks
        chunks_budget = remaining_budget - accumulated_history_tokens

        # 4. Format retrieved chunks sequentially within chunks_budget
        seen_chunk_ids = set()
        chunk_references: list[RetrievedChunk] = []
        concatenated_parts: list[str] = []
        accumulated_chunk_tokens = 0

        for chunk in context_obj.retrieved_chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)

            new_idx = len(chunk_references) + 1
            formatted_chunk = (
                f"[Chunk {new_idx}] Document: {chunk.document_name} (ID: {chunk.document_id})\n"
                f"{chunk.text.strip()}\n\n"
            )
            chunk_tokens = token_estimator.estimate(formatted_chunk)

            if accumulated_chunk_tokens + chunk_tokens > chunks_budget:
                break

            concatenated_parts.append(formatted_chunk)
            chunk_references.append(chunk)
            accumulated_chunk_tokens += chunk_tokens

        concatenated_context = "".join(concatenated_parts).strip()

        # 5. Assemble final prompt messages
        final_messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=system_content)
        ]
        # Append history
        final_messages.extend(history_messages)

        # Append final Turn containing retrieved context and question
        user_content = self._default_user_template.format(
            context=concatenated_context, question=question
        )
        final_messages.append(ChatMessage(role=ChatRole.USER, content=user_content))

        return final_messages, chunk_references

