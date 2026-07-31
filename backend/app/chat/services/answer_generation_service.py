import logging
import time
import uuid
from typing import Any, AsyncIterator
from uuid import UUID

from app.chat.domain.exceptions import NoRelevantContext, TokenBudgetExceeded, PromptTooLarge
from app.chat.domain.interfaces import LLMProvider, TokenEstimator
from app.chat.domain.models import (
    AnswerResponse,
    Citation,
    ConversationContext,
    HistoryRewriteResult,
    MessageRole,
    MessageStatus,
    RetrievalDiagnostics,
    Usage,
)
from app.chat.services.conversation_context_builder import ConversationContextBuilder
from app.chat.services.conversation_manager import ConversationManager
from app.chat.services.prompt_builder import PromptBuilder
from app.core.logger import request_id_ctx
from app.documents.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class AnswerGenerationService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
        token_estimator: TokenEstimator,
        conversation_manager: ConversationManager,
        context_builder: ConversationContextBuilder,
        model: str,
        temperature: float,
        max_response_tokens: int,
        system_prompt_tokens_limit: int,
        max_context_tokens: int,
        reserved_completion_tokens: int,
        max_memory_tokens: int = 3000,
        enable_conversation_memory: bool = True,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.prompt_builder = prompt_builder
        self.llm_provider = llm_provider
        self.token_estimator = token_estimator
        self.conversation_manager = conversation_manager
        self.context_builder = context_builder
        self.model = model
        self.temperature = temperature
        self.max_response_tokens = max_response_tokens
        self.system_prompt_tokens_limit = system_prompt_tokens_limit
        self.max_context_tokens = max_context_tokens
        self.reserved_completion_tokens = reserved_completion_tokens
        self.max_memory_tokens = max_memory_tokens
        self.enable_conversation_memory = enable_conversation_memory

    async def generate_answer(
        self,
        question: str,
        user_id: UUID,
        top_k: int,
        conversation_id: UUID | None = None,
        document_ids: list[UUID] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AnswerResponse:
        start_time = time.perf_counter()

        # 1. Resolve / Create conversation session
        conversation = await self.conversation_manager.get_or_create_conversation(conversation_id, user_id)
        conversation_id = conversation.id

        # Enforce budget checks on system prompt and baseline question size
        system_prompt = self.prompt_builder.get_system_prompt()
        system_tokens = self.token_estimator.estimate(system_prompt)
        if system_tokens > self.system_prompt_tokens_limit:
            raise TokenBudgetExceeded(
                f"System prompt size ({system_tokens}) exceeds limit ({self.system_prompt_tokens_limit})"
            )

        baseline_question = f"Context:\n\n\nQuestion: {question}\n\nAnswer:"
        question_tokens = self.token_estimator.estimate(baseline_question)
        if system_tokens + question_tokens > self.max_context_tokens:
            raise PromptTooLarge("Prompt size exceeds maximum context token budget.")

        # 2. Memory context preparation and query rewriting
        if self.enable_conversation_memory:
            context_obj, rewrite_result = await self.conversation_manager.prepare_context(
                conversation_id, user_id, question
            )
            query_to_retrieve = rewrite_result.rewritten_query
        else:
            context_obj = ConversationContext(conversation=conversation, recent_messages=[])
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="Conversation memory disabled.",
                rewrite_applied=False,
            )
            query_to_retrieve = question

        # 3. Retrieve chunks using the standalone query (Retrieval knows nothing about conversations)
        retrieval_start = time.perf_counter()
        search_result = await self.retrieval_service.retrieve(
            query=query_to_retrieve,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
            filter_metadata=filters,
        )
        retrieval_time_ms = (time.perf_counter() - retrieval_start) * 1000

        # Check if we have no chunks
        if not search_result.retrieved_chunks:
            raise NoRelevantContext("No relevant document context found for the question.")

        # 4. Gather Diagnostics
        dense_count = len(search_result.dense_matches) if search_result.dense_matches else 0
        sparse_count = len(search_result.sparse_matches) if search_result.sparse_matches else 0
        diagnostics = RetrievalDiagnostics(
            rewritten=rewrite_result.rewrite_applied,
            dense_count=dense_count,
            sparse_count=sparse_count,
            fusion_count=len(search_result.retrieved_chunks),
            rerank_count=len(search_result.retrieved_chunks),
            latencies={"retrieval_service": retrieval_time_ms},
        )

        # 5. Build structured ConversationContext
        full_context = self.context_builder.build_context(
            conversation=conversation,
            recent_messages=context_obj.recent_messages,
            summary=context_obj.summary,
            retrieved_chunks=search_result.retrieved_chunks,
            diagnostics=diagnostics,
        )

        # 6. Budget prompts and extract final fitting chunks
        messages, final_chunks = self.prompt_builder.build_prompt(
            context_obj=full_context,
            question=question,
            token_estimator=self.token_estimator,
            max_context_tokens=self.max_context_tokens,
            max_memory_tokens=self.max_memory_tokens,
        )

        if not final_chunks:
            raise NoRelevantContext("No relevant document context fits within the token budget.")

        # 7. Create assistant message in database (status = PENDING)
        assistant_message_id = uuid.uuid4()
        await self.conversation_manager._message_repo.create_assistant_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            role=MessageRole.ASSISTANT,
        )

        # 8. Call LLM Provider
        gen_start_time = time.perf_counter()
        try:
            answer_text, usage = await self.llm_provider.generate(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_response_tokens,
            )
            generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        except Exception as e:
            # Handle failure and persist MessageStatus.FAILED
            await self.conversation_manager._message_repo.fail_message(assistant_message_id, str(e))
            raise

        # 9. Map Citations
        citations = [
            Citation(
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
            )
            for chunk in final_chunks
        ]
        citations_data = [
            {
                "document_id": str(cit.document_id),
                "document_name": cit.document_name,
                "chunk_id": str(cit.chunk_id),
                "chunk_index": cit.chunk_index,
            }
            for cit in citations
        ]

        # 10. Persist completion details (complete message state and trigger summarizer check)
        await self.conversation_manager.finalize_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            assistant_content=answer_text,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            citations=citations_data,
        )

        total_time_ms = (time.perf_counter() - start_time) * 1000

        # Log Observability Metrics
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation completed - RequestID: {req_id} - "
            f"ConversationID: {conversation_id} - "
            f"Model: {self.model} - Chunks: {len(final_chunks)} - "
            f"Rewrite applied: {rewrite_result.rewrite_applied} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms - "
            f"Usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.prompt_tokens + usage.completion_tokens}"
        )

        return AnswerResponse(
            answer=answer_text,
            citations=citations,
            retrieval_time_ms=round(retrieval_time_ms, 2),
            generation_time_ms=round(generation_time_ms, 2),
            total_time_ms=round(total_time_ms, 2),
            model=self.model,
            usage=usage,
            conversation_id=conversation_id,
            diagnostics=diagnostics,
        )

    async def generate_answer_stream(
        self,
        question: str,
        user_id: UUID,
        top_k: int,
        conversation_id: UUID | None = None,
        document_ids: list[UUID] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        start_time = time.perf_counter()

        # 1. Resolve / Create conversation session
        conversation = await self.conversation_manager.get_or_create_conversation(conversation_id, user_id)
        conversation_id = conversation.id

        # Enforce budget checks on system prompt and baseline question size
        system_prompt = self.prompt_builder.get_system_prompt()
        system_tokens = self.token_estimator.estimate(system_prompt)
        if system_tokens > self.system_prompt_tokens_limit:
            raise TokenBudgetExceeded(
                f"System prompt size ({system_tokens}) exceeds limit ({self.system_prompt_tokens_limit})"
            )

        baseline_question = f"Context:\n\n\nQuestion: {question}\n\nAnswer:"
        question_tokens = self.token_estimator.estimate(baseline_question)
        if system_tokens + question_tokens > self.max_context_tokens:
            raise PromptTooLarge("Prompt size exceeds maximum context token budget.")

        # 2. Memory context preparation and query rewriting
        if self.enable_conversation_memory:
            context_obj, rewrite_result = await self.conversation_manager.prepare_context(
                conversation_id, user_id, question
            )
            query_to_retrieve = rewrite_result.rewritten_query
        else:
            context_obj = ConversationContext(conversation=conversation, recent_messages=[])
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="Conversation memory disabled.",
                rewrite_applied=False,
            )
            query_to_retrieve = question

        # 3. Retrieve chunks
        retrieval_start = time.perf_counter()
        search_result = await self.retrieval_service.retrieve(
            query=query_to_retrieve,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
            filter_metadata=filters,
        )
        retrieval_time_ms = (time.perf_counter() - retrieval_start) * 1000

        # Check if we have no chunks
        if not search_result.retrieved_chunks:
            raise NoRelevantContext("No relevant document context found for the question.")

        # 4. Gather Diagnostics
        dense_count = len(search_result.dense_matches) if search_result.dense_matches else 0
        sparse_count = len(search_result.sparse_matches) if search_result.sparse_matches else 0
        diagnostics = RetrievalDiagnostics(
            rewritten=rewrite_result.rewrite_applied,
            dense_count=dense_count,
            sparse_count=sparse_count,
            fusion_count=len(search_result.retrieved_chunks),
            rerank_count=len(search_result.retrieved_chunks),
            latencies={"retrieval_service": retrieval_time_ms},
        )

        # 5. Build structured ConversationContext
        full_context = self.context_builder.build_context(
            conversation=conversation,
            recent_messages=context_obj.recent_messages,
            summary=context_obj.summary,
            retrieved_chunks=search_result.retrieved_chunks,
            diagnostics=diagnostics,
        )

        # 6. Budget prompts
        messages, final_chunks = self.prompt_builder.build_prompt(
            context_obj=full_context,
            question=question,
            token_estimator=self.token_estimator,
            max_context_tokens=self.max_context_tokens,
            max_memory_tokens=self.max_memory_tokens,
        )

        if not final_chunks:
            raise NoRelevantContext("No relevant document context fits within the token budget.")

        # 7. Create assistant message in database (status = PENDING)
        assistant_message_id = uuid.uuid4()
        await self.conversation_manager._message_repo.create_assistant_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            role=MessageRole.ASSISTANT,
        )

        # 8. Map Citations
        citations = [
            Citation(
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
            )
            for chunk in final_chunks
        ]
        citations_data = [
            {
                "document_id": str(cit.document_id),
                "document_name": cit.document_name,
                "chunk_id": str(cit.chunk_id),
                "chunk_index": cit.chunk_index,
            }
            for cit in citations
        ]

        # Yield metadata first event
        yield {
            "event": "metadata",
            "data": {
                "citations": citations_data,
                "retrieval_time_ms": round(retrieval_time_ms, 2),
                "conversation_id": str(conversation_id),
                "diagnostics": diagnostics.model_dump(),
            },
        }

        # 9. LLM Stream
        gen_start_time = time.perf_counter()
        full_answer_list = []
        final_usage = None

        try:
            async for text_delta, usage in self.llm_provider.stream(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_response_tokens,
            ):
                if text_delta:
                    full_answer_list.append(text_delta)
                    # Append chunk to database
                    await self.conversation_manager._message_repo.append_stream_chunk(
                        assistant_message_id, text_delta
                    )
                    yield {
                        "event": "text",
                        "data": {
                            "text": text_delta,
                        },
                    }
                if usage:
                    final_usage = usage
        except Exception as e:
            # Handle failure and persist MessageStatus.FAILED
            await self.conversation_manager._message_repo.fail_message(assistant_message_id, str(e))
            yield {
                "event": "error",
                "data": {
                    "code": "GENERATION_FAILED",
                    "message": f"Error during streaming generation: {e}",
                },
            }
            raise

        generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        total_time_ms = (time.perf_counter() - start_time) * 1000
        full_answer = "".join(full_answer_list)

        # Fallback usage estimation if none was returned by provider
        if not final_usage:
            prompt_tokens_est = self.token_estimator.estimate(str(messages))
            completion_tokens_est = self.token_estimator.estimate(full_answer)
            final_usage = Usage(
                prompt_tokens=prompt_tokens_est,
                completion_tokens=completion_tokens_est,
                total_tokens=prompt_tokens_est + completion_tokens_est,
            )

        # 10. Persist completion details
        await self.conversation_manager.finalize_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            assistant_content=full_answer,
            prompt_tokens=final_usage.prompt_tokens,
            completion_tokens=final_usage.completion_tokens,
            citations=citations_data,
        )

        # Log Observability Metrics
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation stream completed - RequestID: {req_id} - "
            f"ConversationID: {conversation_id} - "
            f"Model: {self.model} - Chunks: {len(final_chunks)} - "
            f"Rewrite applied: {rewrite_result.rewrite_applied} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms - "
            f"Usage: prompt={final_usage.prompt_tokens}, completion={final_usage.completion_tokens}, total={final_usage.prompt_tokens + final_usage.completion_tokens}"
        )

        # Yield final completion event
        yield {
            "event": "done",
            "data": {
                "answer": full_answer,
                "citations": [cit.model_dump() for cit in citations],
                "generation_time_ms": round(generation_time_ms, 2),
                "total_time_ms": round(total_time_ms, 2),
                "model": self.model,
                "usage": final_usage.model_dump(),
                "conversation_id": str(conversation_id),
                "diagnostics": diagnostics.model_dump(),
            },
        }
