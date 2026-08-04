from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_conversation_manager,
    get_current_user_context,
)
from app.chat.domain.exceptions import (
    ConversationNotFoundException,
    UnauthorizedConversationAccessException,
)
from app.chat.domain.models import (
    Conversation,
    ConversationMessage,
    ConversationSettings,
)
from app.chat.services.conversation_manager import ConversationManager

router = APIRouter(tags=["Conversations"])


class ConversationPatchRequest(BaseModel):
    title: str | None = Field(default=None, description="The title of the conversation.")
    settings: ConversationSettings | None = Field(default=None, description="Per-conversation settings.")


class ConversationsListResponse(BaseModel):
    conversations: list[Conversation]
    limit: int
    offset: int


class MessagesListResponse(BaseModel):
    messages: list[ConversationMessage]
    limit: int
    offset: int


@router.get("", response_model=ConversationsListResponse, status_code=status.HTTP_200_OK)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> ConversationsListResponse:
    """
    List all active conversations for the authenticated user, ordered by last activity.
    """
    user_id = UUID(user_context["user_id"])
    conversations = await manager._conversation_repo.list_conversations(
        user_id=user_id, limit=limit, offset=offset
    )
    return ConversationsListResponse(
        conversations=conversations,
        limit=limit,
        offset=offset,
    )


@router.get("/{id}", response_model=Conversation, status_code=status.HTTP_200_OK)
async def get_conversation(
    id: UUID,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Conversation:
    """
    Retrieve a specific conversation session. Checks ownership.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(id, user_id)
        conversation = await manager._conversation_repo.get_conversation(id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {id} not found.",
            )
        return conversation
    except ConversationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.patch("/{id}", response_model=Conversation, status_code=status.HTTP_200_OK)
async def patch_conversation(
    id: UUID,
    request: ConversationPatchRequest,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Conversation:
    """
    Update titles or toggle settings for a specific conversation session.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(id, user_id)
        conversation = await manager._conversation_repo.get_conversation(id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {id} not found.",
            )

        # Apply updates
        if request.title is not None:
            conversation.title = request.title.strip()
        if request.settings is not None:
            conversation.settings = request.settings

        updated = await manager._conversation_repo.update_conversation(conversation)
        return updated
    except ConversationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    id: UUID,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> None:
    """
    Soft-delete a conversation session.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(id, user_id)
        await manager._conversation_repo.delete_conversation(id)
    except ConversationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get("/{id}/messages", response_model=MessagesListResponse, status_code=status.HTTP_200_OK)
async def list_messages(
    id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> MessagesListResponse:
    """
    Get paginated message history for a conversation.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(id, user_id)
        messages = await manager._message_repo.get_recent_messages(
            conversation_id=id, limit=limit, offset=offset
        )
        return MessagesListResponse(
            messages=messages,
            limit=limit,
            offset=offset,
        )
    except ConversationNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
