import inspect
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    check_rate_limit,
    get_conversation_manager,
    get_current_user_context,
    get_document_service,
    get_retrieval_service,
)
from app.chat.services.conversation_manager import ConversationManager
from app.core.config import settings
from app.core.security import PromptInjectionScanner
from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.models import RetrievalMode, RetrievedChunk
from app.documents.services.document_service import DocumentService
from app.documents.services.retrieval_service import RetrievalService

router = APIRouter(tags=["Search"])


class SearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=2000, description="The search query text."
    )
    conversation_id: UUID | None = Field(
        default=None,
        description=(
            "Optional conversation ID. Runs history-aware search AND pins "
            "retrieval to that conversation's own chat-scoped documents."
        ),
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="The maximum number of chunks to return.",
    )
    document_ids: list[UUID] | None = Field(
        default_factory=list,
        max_length=50,
        description="Optional document IDs to restrict search.",
    )
    filters: dict[str, Any] | None = Field(
        default_factory=dict, description="Optional metadata filters."
    )
    retrieval_mode: RetrievalMode | None = Field(
        default=None,
        description="The retrieval mode: 'semantic', 'sparse', 'hybrid', or 'auto'.",
    )


class SearchResponse(BaseModel):
    results: list[RetrievedChunk] = Field(
        ..., description="The ranked list of retrieved document chunks."
    )
    retrieval_time_ms: float = Field(
        ..., description="The total time spent retrieving and ranking in milliseconds."
    )
    total_matches: int = Field(
        ..., description="The total number of matching document chunks."
    )
    conversation_id: UUID = Field(
        ..., description="The conversation ID associated with this search."
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_rate_limit)],
)
async def search_documents(
    request: SearchRequest,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    conversation_manager: ConversationManager = Depends(get_conversation_manager),
    document_service: DocumentService = Depends(get_document_service),
) -> SearchResponse:
    """
    Search document chunks using history-aware hybrid retrieval.
    Returns ranked chunks matching query and filters.
    """
    # Scan search query for injection attempts before processing
    PromptInjectionScanner.scan_prompt(request.query)

    user_id = UUID(user_context["user_id"])

    # 0. Load or create conversation session to retrieve history context.
    # No early commit here: unlike chat (whose SSE metadata event triggers an
    # immediate attachment flush), the search response's conversation_id only
    # leaves at request end, when get_db's teardown has already committed the
    # new row.
    conversation = await conversation_manager.get_or_create_conversation(
        request.conversation_id, user_id
    )
    conversation_id = conversation.id

    # 0b. Resolve the retrieval scope. Explicit document_ids win; otherwise a
    # conversation-scoped search is pinned to that conversation's attachments
    # (global docs never leak in) and a global search is pinned to the user's
    # global docs (chat-scoped docs never leak out). An empty scope skips
    # retrieval entirely — the retrieval service treats a falsy document_ids
    # as "search everything", so passing an empty list would defeat the
    # isolation.
    if request.document_ids:
        retrieval_doc_ids = list(request.document_ids)
    elif request.conversation_id:
        conv_res = document_service.list_documents_by_conversation(
            conversation_id, user_id
        )
        if inspect.isawaitable(conv_res):
            conv_docs = await conv_res
        else:
            conv_docs = conv_res
        retrieval_doc_ids = [doc.id for doc in conv_docs]
    else:
        user_res = document_service.list_documents(user_id)
        if inspect.isawaitable(user_res):
            user_docs = await user_res
        else:
            user_docs = user_res
        retrieval_doc_ids = [doc.id for doc in user_docs]

    # The resolution above mirrors ChatOrchestrator._resolve_retrieval_scope.
    # Build a DocumentRetrievalScope so the RetrievalService enforces scope
    # at the repository layer rather than via the backward-compat fallback.
    from app.documents.domain.models import DocumentRetrievalScope

    # Determine scope intent based on request context:
    # - Explicit document_ids -> library OR conversation intent depending on docs
    # - conversation_id present -> CONVERSATION scope only
    # - no context -> LIBRARY scope (user's global documents)
    has_conversation_scope = bool(request.conversation_id)
    retrieval_scope = DocumentRetrievalScope(
        user_id=user_id,
        conversation_id=conversation_id,
        include_conversation_documents=has_conversation_scope
        or bool(request.document_ids),
        include_library_documents=not has_conversation_scope
        or bool(request.document_ids),
        document_ids=retrieval_doc_ids,
    )

    # Nothing in scope (no docs at all for this user/conversation): return an
    # empty result rather than searching every chunk the user owns. Skipping
    # before the LLM query rewrite mirrors the chat orchestrator's behaviour.
    if not retrieval_doc_ids:
        return SearchResponse(
            results=[],
            retrieval_time_ms=0.0,
            total_matches=0,
            conversation_id=conversation_id,
        )

    # 1. Fetch memory history and rewrite query to standalone form
    recent_messages, _ = await conversation_manager._memory.load_memory(conversation_id)
    rewrite_result = await conversation_manager._rewriter.rewrite(
        request.query, recent_messages
    )
    query_to_retrieve = rewrite_result.rewritten_query

    # 2. Resolve and validate top_k parameter
    top_k = request.top_k
    if top_k is None:
        top_k = settings.DEFAULT_TOP_K
    else:
        if top_k <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="top_k must be a positive integer greater than 0.",
            )
        # Cap top_k at MAX_TOP_K setting
        top_k = min(top_k, settings.MAX_TOP_K)

    # 3. Extract tags and generic metadata filters
    req_filters = request.filters or {}
    tags = req_filters.pop("tags", None)
    # Ensure tags is a list of strings if provided
    if tags is not None and not isinstance(tags, list):
        tags = [str(tags)]

    try:
        # 4. Call RetrievalService with explicit scope (no backward-compat fallback)
        search_result = await retrieval_service.retrieve(
            query=query_to_retrieve,
            user_id=user_id,
            top_k=top_k,
            tags=tags,
            filter_metadata=req_filters,
            retrieval_mode=request.retrieval_mode,
            retrieval_scope=retrieval_scope,
        )

        return SearchResponse(
            results=search_result.retrieved_chunks,
            retrieval_time_ms=round(search_result.retrieval_time * 1000, 2),
            total_matches=search_result.total_matches,
            conversation_id=conversation_id,
        )

    except UnauthorizedDocumentAccess as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Search endpoint exception occurred")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search retrieval pipeline encountered an internal error.",
        )
