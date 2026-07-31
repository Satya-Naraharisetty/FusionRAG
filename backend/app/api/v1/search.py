from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user_context, get_retrieval_service
from app.core.config import settings
from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.models import RetrievedChunk
from app.documents.services.retrieval_service import RetrievalService

router = APIRouter(tags=["Search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The search query text.")
    top_k: int | None = Field(
        default=None, description="The maximum number of chunks to return."
    )
    document_ids: list[UUID] | None = Field(
        default_factory=list, description="Optional document IDs to restrict search."
    )
    filters: dict[str, Any] | None = Field(
        default_factory=dict, description="Optional metadata filters."
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


@router.post("/search", response_model=SearchResponse, status_code=status.HTTP_200_OK)
async def search_documents(
    request: SearchRequest,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    """
    Search document chunks using semantic similarity query.
    Returns ranked chunks matching query and filters.
    """
    user_id = UUID(user_context["user_id"])

    # 1. Resolve and validate top_k parameter
    top_k = request.top_k
    if top_k is None:
        top_k = settings.DEFAULT_TOP_K
    else:
        if top_k <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            query=request.query,
            user_id=user_id,
            top_k=top_k,
            document_ids=request.document_ids,
            tags=tags,
            filter_metadata=req_filters,
        )

        return SearchResponse(
            results=search_result.retrieved_chunks,
            retrieval_time_ms=round(search_result.retrieval_time * 1000, 2),
            total_matches=search_result.total_matches,
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
