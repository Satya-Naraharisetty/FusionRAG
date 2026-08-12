from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_conversation_manager,
    get_current_user_context,
    get_document_service,
    get_retrieval_service,
)
from app.chat.services.conversation_manager import ConversationManager
from app.core.config import settings
from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.models import RetrievalMode, RetrievedChunk
from app.documents.services.document_service import DocumentService
from app.documents.services.retrieval_service import RetrievalService

router = APIRouter(tags=["Search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The search query text.")
    conversation_id: UUID | None = Field(
        default=None,
        description=(
            "Optional conversation ID. Runs history-aware search AND pins "
            "retrieval to that conversation's own chat-scoped documents."
        ),
    )
    top_k: int | None = Field(
        default=None, description="The maximum number of chunks to return."
    )
    document_ids: list[UUID] | None = Field(
        default_factory=list, description="Optional document IDs to restrict search."
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


@router.post("/search", response_model=SearchResponse, status_code=status.HTTP_200_OK)
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

    The two-tier document model is enforced here, mirroring chat retrieval
    (ChatOrchestrator._resolve_retrieval_scope):

    * Chat-scoped documents (uploaded in a conversation) are searchable ONLY
      within their own conversation — pass ``conversation_id`` to search them.
    * Global Documents-section documents are searchable without conversation
      context.
    * Explicit ``document_ids`` are always honored (ownership is verified).
    """
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
        retrieval_doc_ids = [
            doc.id
            for doc in document_service.list_documents_by_conversation(
                conversation_id, user_id
            )
        ]
    else:
        retrieval_doc_ids = [
            doc.id for doc in document_service.list_documents(user_id)
        ]

    # The resolution above mirrors ChatOrchestrator._resolve_retrieval_scope.
    if not retrieval_doc_ids:
        # Nothing in scope (no global docs, or a conversation with no
        # attachments): return an empty result rather than searching every
        # chunk the user owns. Skipping before the LLM query rewrite mirrors
        # the chat orchestrator's skip_rewrite=skip_retrieval — an empty
        # search must not burn a rewrite call whose output would be discarded.
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

    # 1. Resolve and validate top_k parameter
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

    # 2. Extract tags and generic metadata filters
    req_filters = request.filters or {}
    tags = req_filters.pop("tags", None)
    # Ensure tags is a list of strings if provided
    if tags is not None and not isinstance(tags, list):
        tags = [str(tags)]

    try:
        # 3. Call RetrievalService search pipeline
        search_result = await retrieval_service.retrieve(
            query=query_to_retrieve,
            user_id=user_id,
            top_k=top_k,
            document_ids=retrieval_doc_ids,
            tags=tags,
            filter_metadata=req_filters,
            retrieval_mode=request.retrieval_mode,
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
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("Search endpoint exception occurred")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search retrieval pipeline encountered an internal error: {e}",
        )
