import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_answer_generation_service, get_current_user_context
from app.chat.domain.exceptions import (
    LLMProviderError,
    NoRelevantContext,
    PromptTooLarge,
    StreamingCancelled,
    TokenBudgetExceeded,
)
from app.chat.domain.models import AnswerResponse
from app.chat.services.answer_generation_service import AnswerGenerationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question.")
    conversation_id: UUID | None = Field(
        default=None, description="Optional conversation ID to continue a session."
    )
    document_ids: list[UUID] | None = Field(
        default_factory=list, description="Optional document IDs to restrict search."
    )
    top_k: int | None = Field(
        default=None, description="The maximum number of chunks to retrieve."
    )
    filters: dict[str, Any] | None = Field(
        default_factory=dict, description="Optional metadata filters."
    )
    stream: bool = Field(default=False, description="Whether to stream response using SSE.")


@router.post("/chat", response_model=AnswerResponse | None, status_code=status.HTTP_200_OK)
async def chat(
    request: Request,
    chat_req: ChatRequest,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    service: AnswerGenerationService = Depends(get_answer_generation_service),
):
    """
    Orchestration endpoint that retrieves documents and generates a grounded response.
    """
    user_id = UUID(user_context["user_id"])
    top_k = chat_req.top_k or 10

    if not chat_req.stream:
        # Standard synchronous path (exceptions caught by global handlers)
        response = await service.generate_answer(
            question=chat_req.question,
            user_id=user_id,
            top_k=top_k,
            conversation_id=chat_req.conversation_id,
            document_ids=chat_req.document_ids,
            filters=chat_req.filters,
        )
        return response
    else:
        # Server-Sent Events (SSE) streaming path
        async def event_generator():
            try:
                async for event in service.generate_answer_stream(
                    question=chat_req.question,
                    user_id=user_id,
                    top_k=top_k,
                    conversation_id=chat_req.conversation_id,
                    document_ids=chat_req.document_ids,
                    filters=chat_req.filters,
                ):
                    # Check if client closed connection
                    if await request.is_disconnected():
                        logger.warning("Streaming client disconnected. Raising StreamingCancelled.")
                        raise StreamingCancelled("Client disconnected.")

                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            except NoRelevantContext as e:
                yield f"event: error\ndata: {json.dumps({'code': 'NO_RELEVANT_CONTEXT', 'message': str(e)})}\n\n"
            except (PromptTooLarge, TokenBudgetExceeded) as e:
                yield f"event: error\ndata: {json.dumps({'code': 'TOKEN_BUDGET_ERROR', 'message': str(e)})}\n\n"
            except LLMProviderError as e:
                yield f"event: error\ndata: {json.dumps({'code': 'LLM_PROVIDER_ERROR', 'message': str(e)})}\n\n"
            except StreamingCancelled:
                logger.info("Streaming connection closed gracefully after client disconnect.")
            except Exception as e:
                logger.exception("Unhandled error during chat streaming.")
                yield f"event: error\ndata: {json.dumps({'code': 'INTERNAL_ERROR', 'message': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
