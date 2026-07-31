import logging
import time
from typing import Any, AsyncIterator
from uuid import UUID

from app.chat.domain.exceptions import NoRelevantContext, PromptTooLarge, TokenBudgetExceeded
from app.chat.domain.interfaces import LLMProvider, TokenEstimator
from app.chat.domain.models import AnswerResponse, Citation, Usage
from app.chat.services.context_builder import ContextBuilder
from app.chat.services.prompt_builder import PromptBuilder
from app.core.logger import request_id_ctx
from app.documents.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class AnswerGenerationService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        context_builder: ContextBuilder,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
        token_estimator: TokenEstimator,
        model: str,
        temperature: float,
        max_response_tokens: int,
        system_prompt_tokens_limit: int,
        max_context_tokens: int,
        reserved_completion_tokens: int,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.llm_provider = llm_provider
        self.token_estimator = token_estimator
        self.model = model
        self.temperature = temperature
        self.max_response_tokens = max_response_tokens
        self.system_prompt_tokens_limit = system_prompt_tokens_limit
        self.max_context_tokens = max_context_tokens
        self.reserved_completion_tokens = reserved_completion_tokens

    async def generate_answer(
        self,
        question: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AnswerResponse:
        start_time = time.perf_counter()

        # 1. Call RetrievalService
        search_result = await self.retrieval_service.retrieve(
            query=question,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
            filter_metadata=filters,
        )
        retrieval_time_ms = (time.perf_counter() - start_time) * 1000

        # Check if we have no chunks
        if not search_result.retrieved_chunks:
            raise NoRelevantContext("No relevant document context found for the question.")

        # 2. Build context
        grounded_context = self.context_builder.build_context(search_result.retrieved_chunks)
        if not grounded_context.chunk_references:
            raise NoRelevantContext("No relevant document context fits within the token budget.")

        # 3. Build prompts
        messages = self.prompt_builder.build_messages(
            question=question, context=grounded_context.concatenated_context
        )

        # 4. Token Budget Checks
        system_prompt = self.prompt_builder.get_system_prompt()
        sys_tokens = self.token_estimator.estimate(system_prompt)
        if sys_tokens > self.system_prompt_tokens_limit:
            raise TokenBudgetExceeded(
                f"System prompt token estimate ({sys_tokens}) exceeds the limit ({self.system_prompt_tokens_limit})."
            )

        user_prompt = messages[1].content
        user_prompt_tokens = self.token_estimator.estimate(user_prompt)
        total_prompt_tokens = sys_tokens + user_prompt_tokens

        max_allowed_prompt_tokens = self.system_prompt_tokens_limit + self.max_context_tokens
        if total_prompt_tokens > max_allowed_prompt_tokens:
            raise PromptTooLarge(
                f"Total prompt token estimate ({total_prompt_tokens}) exceeds maximum allowed prompt tokens ({max_allowed_prompt_tokens})."
            )

        # 5. Invoke LLM Provider
        gen_start_time = time.perf_counter()
        answer_text, usage = await self.llm_provider.generate(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_response_tokens,
        )
        generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        total_time_ms = (time.perf_counter() - start_time) * 1000

        # 6. Map Citations Deterministically
        citations = [
            Citation(
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
            )
            for chunk in grounded_context.chunk_references
        ]

        # 7. Observability Logging (safe, no content/keys/prompts logged)
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation completed - RequestID: {req_id} - "
            f"Model: {self.model} - Chunks: {len(grounded_context.chunk_references)} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms - "
            f"Usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}"
        )

        return AnswerResponse(
            answer=answer_text,
            citations=citations,
            retrieval_time_ms=round(retrieval_time_ms, 2),
            generation_time_ms=round(generation_time_ms, 2),
            total_time_ms=round(total_time_ms, 2),
            model=self.model,
            usage=usage,
        )

    async def generate_answer_stream(
        self,
        question: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict]:
        start_time = time.perf_counter()

        # 1. Call RetrievalService
        search_result = await self.retrieval_service.retrieve(
            query=question,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
            filter_metadata=filters,
        )
        retrieval_time_ms = (time.perf_counter() - start_time) * 1000

        # Check if we have no chunks
        if not search_result.retrieved_chunks:
            raise NoRelevantContext("No relevant document context found for the question.")

        # 2. Build context
        grounded_context = self.context_builder.build_context(search_result.retrieved_chunks)
        if not grounded_context.chunk_references:
            raise NoRelevantContext("No relevant document context fits within the token budget.")

        # 3. Build prompts
        messages = self.prompt_builder.build_messages(
            question=question, context=grounded_context.concatenated_context
        )

        # 4. Token Budget Checks
        system_prompt = self.prompt_builder.get_system_prompt()
        sys_tokens = self.token_estimator.estimate(system_prompt)
        if sys_tokens > self.system_prompt_tokens_limit:
            raise TokenBudgetExceeded(
                f"System prompt token estimate ({sys_tokens}) exceeds the limit ({self.system_prompt_tokens_limit})."
            )

        user_prompt = messages[1].content
        user_prompt_tokens = self.token_estimator.estimate(user_prompt)
        total_prompt_tokens = sys_tokens + user_prompt_tokens

        max_allowed_prompt_tokens = self.system_prompt_tokens_limit + self.max_context_tokens
        if total_prompt_tokens > max_allowed_prompt_tokens:
            raise PromptTooLarge(
                f"Total prompt token estimate ({total_prompt_tokens}) exceeds maximum allowed prompt tokens ({max_allowed_prompt_tokens})."
            )

        # Map Citations Deterministically
        citations = [
            Citation(
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
            )
            for chunk in grounded_context.chunk_references
        ]

        # Yield metadata first event
        yield {
            "event": "metadata",
            "data": {
                "citations": [cit.model_dump() for cit in citations],
                "retrieval_time_ms": round(retrieval_time_ms, 2),
            },
        }

        # 5. Invoke LLM provider stream
        gen_start_time = time.perf_counter()
        full_answer_list = []
        final_usage = None

        async for text_delta, usage in self.llm_provider.stream(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_response_tokens,
        ):
            if text_delta:
                full_answer_list.append(text_delta)
                yield {
                    "event": "text",
                    "data": {
                        "text": text_delta
                    },
                }
            if usage:
                final_usage = usage

        generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        total_time_ms = (time.perf_counter() - start_time) * 1000
        full_answer = "".join(full_answer_list)

        # Fallback usage if not returned by provider
        if not final_usage:
            # Estimate heuristically
            final_usage = Usage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=self.token_estimator.estimate(full_answer),
                total_tokens=total_prompt_tokens + self.token_estimator.estimate(full_answer),
            )

        # 6. Logging observability metrics
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation stream completed - RequestID: {req_id} - "
            f"Model: {self.model} - Chunks: {len(grounded_context.chunk_references)} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms - "
            f"Usage: prompt={final_usage.prompt_tokens}, completion={final_usage.completion_tokens}, total={final_usage.total_tokens}"
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
            },
        }
