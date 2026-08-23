import inspect
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.chat.domain.agents import ToolContext
from app.chat.domain.exceptions import (
    PromptTooLarge,
    StreamingCancelled,
    TokenBudgetExceeded,
)
from app.chat.domain.models import (
    AnswerResponse,
    Citation,
    ConversationContext,
    HistoryRewriteResult,
    MessageRole,
    RetrievalDiagnostics,
    Usage,
)
from app.chat.services.agent_executor import AgentExecutor
from app.chat.services.conversation_context_builder import ConversationContextBuilder
from app.chat.services.conversation_manager import ConversationManager
from app.chat.services.llm_generation_service import LLMGenerationService
from app.chat.services.prompt_builder import PromptBuilder
from app.core.logger import request_id_ctx
from app.documents.domain.models import DocumentRetrievalScope, SearchResult
from app.documents.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class ChatOrchestrator:
    # Case-insensitive mention that marks a question as "documents first": the
    # uploaded documents become the priority source and, if the question is not
    # covered by them, the assistant must say so in its reply.
    _DOCUMENTS_MENTION_PATTERN = re.compile(r"(?<!\w)@documents\b", re.IGNORECASE)

    @classmethod
    def _parse_documents_mention(cls, question: str) -> tuple[str, bool]:
        """
        Detect and strip the @documents priority mention from a question.

        Returns ``(cleaned_question, documents_priority)``. The mention is a
        control directive, so it is removed before retrieval, prompt building
        and persistence.
        """
        priority = bool(cls._DOCUMENTS_MENTION_PATTERN.search(question))
        cleaned = cls._DOCUMENTS_MENTION_PATTERN.sub(" ", question)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            # The message was only the mention itself (e.g. "@documents"). Keep
            # the raw text so an empty question never reaches persistence,
            # retrieval or the LLM prompt.
            return question, False
        return cleaned, priority

    async def _ensure_conversation_durable(self) -> None:
        """
        Make a just-created conversation durable BEFORE its id leaves this
        process. The streaming path announces the id in the first SSE metadata
        event, and the frontend flushes its queued chat attachments the moment
        that id arrives — their upload request verifies ownership and would
        404 on an uncommitted row (the request-scoped session only commits at
        teardown, which for a StreamingResponse is after the stream
        finishes). The repository is deliberately flush-only; committing here,
        at the point the orchestrator is about to expose the id, is the
        caller's job.

        No-op when the conversation already existed (nothing is pending in the
        session at this point) and when the manager is not backed by a
        SQLAlchemy repository (unit tests use session-less fakes). If the
        manager IS repo-backed but the session can't be resolved, log a
        warning instead of failing — a wiring mistake must stay observable
        rather than silently resurrect the 404.
        """
        repo = getattr(self.conversation_manager, "_conversation_repo", None)
        db = getattr(repo, "_db", None)
        if db is not None:
            await db.commit()
        elif repo is not None:
            logger.warning(
                "Could not resolve DB session to commit a new conversation "
                "(repo has no _db); its id is leaving the process uncommitted."
            )

    async def _resolve_retrieval_scope(
        self,
        conversation_id: UUID | None,
        user_id: UUID,
        document_ids: list[UUID] | None,
        documents_priority: bool,
    ) -> list[UUID]:
        """
        Decide what to retrieve under the two-tier document model.

        Returns the explicit document ids to search (empty means "skip
        retrieval entirely"):

        * Chat-scoped documents (``conversation_id`` set on the document) are
          ALWAYS retrieved in their own conversation — no @documents mention
          needed.
        * The user's global documents are only included when the @documents
          mention was used (``documents_priority``) or explicit
          ``document_ids`` were passed.

        Always returning an explicit id list (instead of None for "everything")
        keeps chat-scoped documents isolated: a mention can never spill another
        conversation's attachments into this one.
        """
        scoped_doc_ids = await self._load_conversation_documents(
            conversation_id, user_id
        )

        if documents_priority or document_ids:
            if document_ids:
                global_doc_ids = list(document_ids)
            else:
                global_doc_ids = await self._load_global_documents(user_id)
        else:
            global_doc_ids = []

        # Deduplicate while preserving order (chat-scoped first).
        return list(dict.fromkeys([*scoped_doc_ids, *global_doc_ids]))

    async def _load_conversation_documents(
        self, conversation_id: UUID | None, user_id: UUID
    ) -> list[UUID]:
        """
        Ids of documents scoped to the given conversation. Best-effort: any
        failure (or a missing document service, e.g. in tests) degrades to
        "no scoped documents" rather than failing the chat request.
        """
        if not conversation_id:
            return []
        doc_service = getattr(self.conversation_manager, "_document_service", None)
        if doc_service is None:
            return []
        try:
            docs = doc_service.list_documents_by_conversation(conversation_id, user_id)
            if inspect.isawaitable(docs):
                docs = await docs
            return [doc.id for doc in docs]
        except Exception:
            logger.exception(
                "Failed to load conversation-scoped documents for %s",
                conversation_id,
            )
            return []

    async def _load_global_documents(self, user_id: UUID) -> list[UUID]:
        """
        Ids of the user's global (Documents-section) documents. Best-effort:
        a failure degrades to "no global documents" rather than failing the
        request.
        """
        doc_service = getattr(self.conversation_manager, "_document_service", None)
        if doc_service is None:
            return []
        try:
            docs = doc_service.list_documents(user_id)
            if inspect.isawaitable(docs):
                docs = await docs
            return [doc.id for doc in docs]
        except Exception:
            logger.exception("Failed to load global documents for %s", user_id)
            return []

    def __init__(
        self,
        retrieval_service: RetrievalService,
        prompt_builder: PromptBuilder,
        llm_generation_service: LLMGenerationService,
        token_estimator: Any,
        conversation_manager: ConversationManager,
        context_builder: ConversationContextBuilder,
        agent_executor: AgentExecutor,
        master_agent: Any | None = None,
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.0,
        max_response_tokens: int = 1000,
        system_prompt_tokens_limit: int = 1000,
        max_context_tokens: int = 4000,
        reserved_completion_tokens: int = 500,
        max_memory_tokens: int = 3000,
        enable_conversation_memory: bool = True,
        enable_tool_calling: bool = True,
        enable_multi_agent: bool = True,
        adaptive_rag_orchestrator: Any | None = None,
        enable_adaptive_rag: bool | None = None,
    ) -> None:
        from app.core.config import settings

        self.retrieval_service = retrieval_service
        self.prompt_builder = prompt_builder
        self.llm_generation_service = llm_generation_service
        self.token_estimator = token_estimator
        self.conversation_manager = conversation_manager
        self.context_builder = context_builder
        self.agent_executor = agent_executor
        self.master_agent = master_agent
        self.model = model
        self.temperature = temperature
        self.max_response_tokens = max_response_tokens
        self.system_prompt_tokens_limit = system_prompt_tokens_limit
        self.max_context_tokens = max_context_tokens
        self.reserved_completion_tokens = reserved_completion_tokens
        self.max_memory_tokens = max_memory_tokens
        self.enable_conversation_memory = enable_conversation_memory
        self.enable_tool_calling = enable_tool_calling
        self.enable_multi_agent = enable_multi_agent
        self.adaptive_rag_orchestrator = adaptive_rag_orchestrator
        self.enable_adaptive_rag = (
            enable_adaptive_rag
            if enable_adaptive_rag is not None
            else getattr(settings, "ENABLE_ADAPTIVE_RAG", False)
        )

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

        # Strip the @documents priority mention (if present) before any
        # processing so it never leaks into retrieval, prompts or history.
        question, documents_priority = self._parse_documents_mention(question)

        # 1. Resolve / Create conversation session
        conversation = await self.conversation_manager.get_or_create_conversation(
            conversation_id, user_id
        )
        conversation_id = conversation.id
        # A brand-new conversation must be committed before its id leaves this
        # process (the streaming path announces it in the first SSE metadata
        # event, which triggers the frontend's attachment flush).
        await self._ensure_conversation_durable()

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

        # 2. Resolve the retrieval scope under the two-tier document model.
        # Chat-scoped documents (uploaded in THIS conversation) are always part
        # of its retrieval — no @documents mention needed. The user's global
        # documents (Documents section) are only searched when the @documents
        # mention was used (or explicit document_ids were passed). Everything
        # else answers from general knowledge: retrieval and the LLM
        # query-rewrite that feeds it are both skipped (see PromptBuilder
        # _NO_CONTEXT_NOTE). Resolving the scope here (before prepare_context)
        # lets skip_rewrite match the retrieval decision.
        retrieval_doc_ids = await self._resolve_retrieval_scope(
            conversation_id=conversation_id,
            user_id=user_id,
            document_ids=document_ids,
            documents_priority=documents_priority,
        )
        skip_retrieval = not bool(retrieval_doc_ids)

        if self.enable_conversation_memory:
            (
                context_obj,
                rewrite_result,
            ) = await self.conversation_manager.prepare_context(
                conversation_id, user_id, question, skip_rewrite=skip_retrieval
            )
            query_to_retrieve = rewrite_result.rewritten_query
        else:
            context_obj = ConversationContext(
                conversation=conversation, recent_messages=[]
            )
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="Conversation memory disabled.",
                rewrite_applied=False,
            )
            query_to_retrieve = question

        # 3. Retrieve chunks using the standalone query
        retrieval_start = time.perf_counter()
        if skip_retrieval:
            # Nothing to search (no chat-scoped documents and no @documents
            # mention): the prompt builder relaxes the context rule so the LLM
            # answers from general knowledge.
            search_result = SearchResult(
                original_query=query_to_retrieve,
                retrieval_time=0.0,
                total_matches=0,
                retrieved_chunks=[],
                dense_matches=[],
                sparse_matches=[],
            )
        else:
            retrieval_scope = DocumentRetrievalScope(
                user_id=user_id,
                conversation_id=conversation_id,
                include_conversation_documents=True,
                include_library_documents=documents_priority,
                document_ids=retrieval_doc_ids if retrieval_doc_ids else None,
            )
            if self.enable_adaptive_rag and self.adaptive_rag_orchestrator is not None:
                search_result = await self.adaptive_rag_orchestrator.orchestrate(
                    query=query_to_retrieve,
                    user_id=user_id,
                    top_k=top_k,
                    conversation_id=conversation_id,
                    document_ids=retrieval_doc_ids if retrieval_doc_ids else None,
                    filter_metadata=filters,
                    retrieval_scope=retrieval_scope,
                )
            else:
                search_result = await self.retrieval_service.retrieve(
                    query=query_to_retrieve,
                    user_id=user_id,
                    top_k=top_k,
                    filter_metadata=filters,
                    retrieval_scope=retrieval_scope,
                )
        retrieval_time_ms = (time.perf_counter() - retrieval_start) * 1000

        # Note: an empty retrieval does NOT abort the request. The prompt is
        # built with an empty context and the assistant answers from general
        # knowledge (calling out the gap when @documents was used).

        # 4. Gather Diagnostics
        dense_count = (
            len(search_result.dense_matches) if search_result.dense_matches else 0
        )
        sparse_count = (
            len(search_result.sparse_matches) if search_result.sparse_matches else 0
        )
        diagnostics = RetrievalDiagnostics(
            rewritten=rewrite_result.rewrite_applied,
            retrieval_skipped=skip_retrieval,
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
            document_priority=documents_priority,
        )

        # If final_chunks is empty, citations will be empty and the assistant
        # answers from general knowledge (see PromptBuilder instructions).

        # 7. Create assistant message in database (status = PENDING)
        assistant_message_id = uuid.uuid4()
        await self.conversation_manager._message_repo.create_assistant_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            role=MessageRole.ASSISTANT,
        )

        # 8. Call LLM, Multi-Agent, or Single-Agent Loop
        gen_start_time = time.perf_counter()
        try:
            if self.enable_multi_agent and self.master_agent is not None:
                from app.chat.domain.multi_agent import AgentExecutionContext

                agent_ctx = AgentExecutionContext(
                    request_id=request_id_ctx.get() or str(uuid.uuid4()),
                    user_id=user_id,
                    conversation_id=conversation_id,
                    include_library_documents=documents_priority,
                    include_conversation_documents=True,
                    document_ids=retrieval_doc_ids,
                )
                multi_resp = await self.master_agent.execute_request(
                    request=question,
                    context=agent_ctx,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_response_tokens,
                )
                answer_text = multi_resp.answer
                usage = multi_resp.usage
                if multi_resp.citations:
                    citations = multi_resp.citations
            elif self.enable_tool_calling and final_chunks:
                # Instantiate thread-safe execution context
                tool_context = ToolContext(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    db_session=self.conversation_manager._conversation_repo._db,  # type: ignore[attr-defined]  # access underlying SQLAlchemy Session
                    # Explicit retrieval intent: set from the @documents mention.
                    # This is the only authoritative source for agent tools;
                    # never derived from model-supplied document IDs.
                    include_library_documents=documents_priority,
                    include_conversation_documents=True,
                )
                agent_resp = await self.agent_executor.execute(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_response_tokens,
                    context=tool_context,
                )
                answer_text = agent_resp.answer
                usage = Usage(
                    prompt_tokens=agent_resp.total_prompt_tokens,
                    completion_tokens=agent_resp.total_completion_tokens,
                    total_tokens=agent_resp.total_prompt_tokens
                    + agent_resp.total_completion_tokens,
                )
            else:
                response = await self.llm_generation_service.generate(
                    messages=messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_response_tokens,
                )
                from app.chat.domain.interfaces import ProviderResponse

                if isinstance(response, tuple) and not hasattr(response, "content"):
                    response = ProviderResponse(content=response[0], usage=response[1])
                answer_text = response.content
                usage = response.usage

            generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        except Exception as e:
            await self.conversation_manager._message_repo.fail_message(
                assistant_message_id, str(e)
            )
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

        total_time_ms = (time.perf_counter() - start_time) * 1000
        metadata = {
            "retrieval_time_ms": retrieval_time_ms,
            "generation_time_ms": generation_time_ms,
            "total_time_ms": total_time_ms,
        }

        # 10. Persist completion details
        await self.conversation_manager.finalize_message(
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            assistant_content=answer_text,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            citations=citations_data,
            metadata=metadata,
        )

        # Log Observability Metrics
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation completed - RequestID: {req_id} - "
            f"ConversationID: {conversation_id} - "
            f"Model: {self.model} - AgentEnabled: {self.enable_tool_calling} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms - "
            f"Usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}"
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

        # Strip the @documents priority mention (if present) before any
        # processing so it never leaks into retrieval, prompts or history.
        question, documents_priority = self._parse_documents_mention(question)

        # 1. Resolve / Create conversation session
        conversation = await self.conversation_manager.get_or_create_conversation(
            conversation_id, user_id
        )
        conversation_id = conversation.id
        # A brand-new conversation must be committed before its id leaves this
        # process (the streaming path announces it in the first SSE metadata
        # event, which triggers the frontend's attachment flush).
        await self._ensure_conversation_durable()

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

        # 2. Resolve the retrieval scope under the two-tier document model.
        # Chat-scoped documents (uploaded in THIS conversation) are always part
        # of its retrieval — no @documents mention needed. The user's global
        # documents (Documents section) are only searched when the @documents
        # mention was used (or explicit document_ids were passed). Everything
        # else answers from general knowledge: retrieval and the LLM
        # query-rewrite that feeds it are both skipped.
        retrieval_doc_ids = await self._resolve_retrieval_scope(
            conversation_id=conversation_id,
            user_id=user_id,
            document_ids=document_ids,
            documents_priority=documents_priority,
        )
        skip_retrieval = not bool(retrieval_doc_ids)

        if self.enable_conversation_memory:
            (
                context_obj,
                rewrite_result,
            ) = await self.conversation_manager.prepare_context(
                conversation_id, user_id, question, skip_rewrite=skip_retrieval
            )
            query_to_retrieve = rewrite_result.rewritten_query
        else:
            context_obj = ConversationContext(
                conversation=conversation, recent_messages=[]
            )
            rewrite_result = HistoryRewriteResult(
                original_query=question,
                rewritten_query=question,
                rewrite_reason="Conversation memory disabled.",
                rewrite_applied=False,
            )
            query_to_retrieve = question

        # 3. Retrieve chunks
        retrieval_start = time.perf_counter()
        if skip_retrieval:
            # Nothing to search (no chat-scoped documents and no @documents
            # mention): the prompt builder relaxes the context rule so the LLM
            # answers from general knowledge.
            search_result = SearchResult(
                original_query=query_to_retrieve,
                retrieval_time=0.0,
                total_matches=0,
                retrieved_chunks=[],
                dense_matches=[],
                sparse_matches=[],
            )
        else:
            retrieval_scope = DocumentRetrievalScope(
                user_id=user_id,
                conversation_id=conversation_id,
                include_conversation_documents=True,
                include_library_documents=documents_priority,
                document_ids=retrieval_doc_ids if retrieval_doc_ids else None,
            )
            if self.enable_adaptive_rag and self.adaptive_rag_orchestrator is not None:
                search_result = await self.adaptive_rag_orchestrator.orchestrate(
                    query=query_to_retrieve,
                    user_id=user_id,
                    top_k=top_k,
                    conversation_id=conversation_id,
                    document_ids=retrieval_doc_ids if retrieval_doc_ids else None,
                    filter_metadata=filters,
                    retrieval_scope=retrieval_scope,
                )
            else:
                search_result = await self.retrieval_service.retrieve(
                    query=query_to_retrieve,
                    user_id=user_id,
                    top_k=top_k,
                    filter_metadata=filters,
                    retrieval_scope=retrieval_scope,
                )
        retrieval_time_ms = (time.perf_counter() - retrieval_start) * 1000

        # Note: an empty retrieval does NOT abort the request. The prompt is
        # built with an empty context and the assistant answers from general
        # knowledge (calling out the gap when @documents was used).

        # 4. Gather Diagnostics
        dense_count = (
            len(search_result.dense_matches) if search_result.dense_matches else 0
        )
        sparse_count = (
            len(search_result.sparse_matches) if search_result.sparse_matches else 0
        )
        diagnostics = RetrievalDiagnostics(
            rewritten=rewrite_result.rewrite_applied,
            retrieval_skipped=skip_retrieval,
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
            document_priority=documents_priority,
        )

        # If final_chunks is empty, citations will be empty and the assistant
        # answers from general knowledge (see PromptBuilder instructions).

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

        message_finalized = False

        async def _mark_interrupted_if_incomplete() -> None:
            """
            Persist any partially streamed assistant output in a terminal state
            when the stream ends abnormally (client disconnect, task
            cancellation, or any other unexpected exit).
            """
            if message_finalized:
                return
            try:
                await self.conversation_manager._message_repo.interrupt_message(
                    assistant_message_id, reason="client_disconnected"
                )
            except Exception:
                logger.exception(
                    "Failed to mark interrupted assistant message %s",
                    assistant_message_id,
                )

        try:
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

            # 9. Execute streaming flow (Multi-Agent, Single-Agent, or Standard)
            gen_start_time = time.perf_counter()
            full_answer_list = []
            final_usage = None

            try:
                if self.enable_multi_agent and self.master_agent is not None:
                    from app.chat.domain.multi_agent import AgentExecutionContext

                    agent_ctx = AgentExecutionContext(
                        request_id=request_id_ctx.get() or str(uuid.uuid4()),
                        user_id=user_id,
                        conversation_id=conversation_id,
                        include_library_documents=documents_priority,
                        include_conversation_documents=True,
                        document_ids=retrieval_doc_ids,
                    )
                    async for event in self.master_agent.execute_request_stream(
                        request=question,
                        context=agent_ctx,
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_response_tokens,
                    ):
                        if event.get("event") == "text":
                            text_val = event["data"]["text"]
                            full_answer_list.append(text_val)
                            await self.conversation_manager._message_repo.append_stream_chunk(
                                assistant_message_id, text_val
                            )
                        elif event.get("event") == "synthesis_done":
                            if "usage" in event.get("data", {}):
                                u_data = event["data"]["usage"]
                                final_usage = Usage(
                                    prompt_tokens=u_data.get("prompt_tokens", 0),
                                    completion_tokens=u_data.get(
                                        "completion_tokens", 0
                                    ),
                                    total_tokens=u_data.get("total_tokens", 0),
                                )
                        yield event
                elif self.enable_tool_calling and final_chunks:
                    tool_context = ToolContext(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        db_session=self.conversation_manager._conversation_repo._db,  # type: ignore[attr-defined]
                        # Explicit retrieval intent: set from the @documents mention.
                        # This is the only authoritative source for agent tools;
                        # never derived from model-supplied document IDs.
                        include_library_documents=documents_priority,
                        include_conversation_documents=True,
                    )
                    async for event in self.agent_executor.execute_stream(
                        messages=messages,
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_response_tokens,
                        context=tool_context,
                    ):
                        # Intercept text chunks to update pending DB record
                        if event["event"] == "text":
                            text_val = event["data"]["text"]
                            full_answer_list.append(text_val)
                            await self.conversation_manager._message_repo.append_stream_chunk(
                                assistant_message_id, text_val
                            )
                        # Propagate event
                        yield event

                        if event["event"] == "done":
                            final_usage = Usage(
                                prompt_tokens=event["data"]["usage"]["prompt_tokens"],
                                completion_tokens=event["data"]["usage"][
                                    "completion_tokens"
                                ],
                                total_tokens=event["data"]["usage"]["total_tokens"],
                            )
                else:
                    async for chunk in self.llm_generation_service.stream(
                        messages=messages,
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_response_tokens,
                    ):
                        from app.chat.domain.interfaces import StreamChunk

                        if isinstance(chunk, tuple) and not hasattr(
                            chunk, "text_delta"
                        ):
                            chunk = StreamChunk(text_delta=chunk[0], usage=chunk[1])
                        text_delta = chunk.text_delta
                        if text_delta:
                            full_answer_list.append(text_delta)
                            await self.conversation_manager._message_repo.append_stream_chunk(
                                assistant_message_id, text_delta
                            )
                            yield {
                                "event": "text",
                                "data": {
                                    "text": text_delta,
                                },
                            }
                        if chunk.usage:
                            final_usage = chunk.usage

                generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
                total_time_ms = (time.perf_counter() - start_time) * 1000
                full_answer = "".join(full_answer_list)

                if not final_usage:
                    prompt_tokens_est = self.token_estimator.estimate(str(messages))
                    completion_tokens_est = self.token_estimator.estimate(full_answer)
                    final_usage = Usage(
                        prompt_tokens=prompt_tokens_est,
                        completion_tokens=completion_tokens_est,
                        total_tokens=prompt_tokens_est + completion_tokens_est,
                    )

                metadata = {
                    "retrieval_time_ms": retrieval_time_ms,
                    "generation_time_ms": generation_time_ms,
                    "total_time_ms": total_time_ms,
                }
                # Persist standard completion details
                await self.conversation_manager.finalize_message(
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    assistant_content=full_answer,
                    prompt_tokens=final_usage.prompt_tokens,
                    completion_tokens=final_usage.completion_tokens,
                    citations=citations_data,
                    metadata=metadata,
                )
                message_finalized = True

                # Yield done event
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
            except StreamingCancelled:
                # Client-initiated disconnect. Let the outer finally persist the
                # partial answer as INTERRUPTED rather than marking it FAILED.
                raise
            except Exception as e:
                await self.conversation_manager._message_repo.fail_message(
                    assistant_message_id, str(e)
                )
                message_finalized = True
                yield {
                    "event": "error",
                    "data": {
                        "code": "GENERATION_FAILED",
                        "message": f"Error during streaming generation: {e}",
                    },
                }
                raise

            # Finalize message database record if using agentic tool calling
            if self.enable_tool_calling and final_usage:
                full_answer = "".join(full_answer_list)
                generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
                total_time_ms = (time.perf_counter() - start_time) * 1000
                metadata = {
                    "retrieval_time_ms": retrieval_time_ms,
                    "generation_time_ms": generation_time_ms,
                    "total_time_ms": total_time_ms,
                }
                await self.conversation_manager.finalize_message(
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    assistant_content=full_answer,
                    prompt_tokens=final_usage.prompt_tokens,
                    completion_tokens=final_usage.completion_tokens,
                    citations=citations_data,
                    metadata=metadata,
                )
                message_finalized = True
        finally:
            await _mark_interrupted_if_incomplete()

        generation_time_ms = (time.perf_counter() - gen_start_time) * 1000
        total_time_ms = (time.perf_counter() - start_time) * 1000

        # Log Observability Metrics
        req_id = request_id_ctx.get() or "N/A"
        logger.info(
            f"Answer generation stream completed - RequestID: {req_id} - "
            f"ConversationID: {conversation_id} - "
            f"Model: {self.model} - AgentEnabled: {self.enable_tool_calling} - "
            f"Retrieval latency: {retrieval_time_ms:.2f}ms - "
            f"Generation latency: {generation_time_ms:.2f}ms - "
            f"Total latency: {total_time_ms:.2f}ms"
        )
