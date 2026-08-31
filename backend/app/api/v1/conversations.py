from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    check_rate_limit,
    get_conversation_manager,
    get_current_user_context,
    get_document_service,
)
from app.api.v1.documents import DocumentResponse
from app.chat.domain.exceptions import (
    ConversationNotFoundException,
    UnauthorizedConversationAccessException,
)
from app.chat.domain.models import (
    Conversation,
    ConversationMessage,
    ConversationSettings,
    ConversationState,
)
from app.chat.services.conversation_manager import ConversationManager
from app.core.pagination import InvalidCursorException
from app.documents.services.document_service import DocumentService

router = APIRouter(tags=["Conversations"])


class ConversationPatchRequest(BaseModel):
    title: str | None = Field(
        default=None, description="The title of the conversation."
    )
    settings: ConversationSettings | None = Field(
        default=None, description="Per-conversation settings."
    )


class ConversationsListResponse(BaseModel):
    items: list[Conversation] = Field(default_factory=list)
    conversations: list[Conversation] = Field(default_factory=list)
    limit: int
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_next_page: bool = False
    has_prev_page: bool = False
    has_more: bool = False


class MessagesListResponse(BaseModel):
    items: list[ConversationMessage] = Field(default_factory=list)
    messages: list[ConversationMessage] = Field(default_factory=list)
    limit: int
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_next_page: bool = False
    has_prev_page: bool = False
    has_more: bool = False


class DeleteMessagesResponse(BaseModel):
    deleted_count: int


@router.get(
    "", response_model=ConversationsListResponse, status_code=status.HTTP_200_OK
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, description="Signed opaque keyset cursor"),
    offset: int | None = Query(
        default=None,
        description="Deprecated legacy offset - explicitly rejected",
        include_in_schema=False,
    ),
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> ConversationsListResponse:
    """
    List all active conversations for the authenticated user with canonical keyset pagination.
    """
    if offset is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Legacy offset pagination is not supported. Use keyset cursor pagination.",
        )
    user_id = UUID(user_context["user_id"])
    try:
        page = await manager.list_conversations(
            user_id=user_id, limit=limit, cursor=cursor
        )
        return ConversationsListResponse(
            items=page.items,
            conversations=page.items,
            limit=page.limit,
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            has_next_page=page.has_next_page,
            has_prev_page=page.has_prev_page,
            has_more=page.has_more,
        )
    except InvalidCursorException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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
        conversation = await manager.get_conversation(id, user_id)
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
        updated = await manager.patch_conversation(
            conversation_id=id,
            user_id=user_id,
            title=request.title,
            settings=request.settings,
        )
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
    Soft-delete a conversation session and all associated documents.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(id, user_id)
        await manager.delete_conversation(id, user_id)
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


@router.get(
    "/{id}/messages",
    response_model=MessagesListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_messages(
    id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, description="Signed opaque keyset cursor"),
    offset: int | None = Query(
        default=None,
        description="Deprecated legacy offset - explicitly rejected",
        include_in_schema=False,
    ),
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> MessagesListResponse:
    """
    Get paginated message history for a conversation with canonical keyset pagination.
    """
    if offset is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Legacy offset pagination is not supported. Use keyset cursor pagination.",
        )
    user_id = UUID(user_context["user_id"])
    try:
        page = await manager.list_messages(
            conversation_id=id,
            user_id=user_id,
            limit=limit,
            cursor=cursor,
        )
        return MessagesListResponse(
            items=page.items,
            messages=page.items,
            limit=page.limit,
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            has_next_page=page.has_next_page,
            has_prev_page=page.has_prev_page,
            has_more=page.has_more,
        )
    except InvalidCursorException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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


@router.delete(
    "/{id}/messages/{message_id}",
    response_model=DeleteMessagesResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_messages_from(
    id: UUID,
    message_id: UUID,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> DeleteMessagesResponse:
    """
    Delete a message and all subsequent messages in the conversation (ChatGPT-style edit truncation).
    """
    user_id = UUID(user_context["user_id"])
    try:
        count = await manager.delete_messages_from(
            conversation_id=id, user_id=user_id, message_id=message_id
        )
        return DeleteMessagesResponse(deleted_count=count)
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


@router.post(
    "/{conversation_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_rate_limit)],
)
async def upload_conversation_document(
    conversation_id: UUID,
    file: UploadFile = File(...),
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Upload a document scoped to a specific conversation (scope = CONVERSATION).
    Verifies that the caller owns the conversation.
    """
    user_id = UUID(user_context["user_id"])

    try:
        conv = await manager.get_conversation(conversation_id, user_id)
        if conv.state in (ConversationState.DELETED, ConversationState.ARCHIVED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot upload documents to a deleted or archived conversation.",
            )
    except ConversationNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    file_bytes = await file.read()

    from app.documents.domain.models import DocumentScope

    try:
        document = await document_service.upload_document(
            original_filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
            user_id=user_id,
            scope=DocumentScope.CONVERSATION,
            conversation_id=conversation_id,
        )
        return DocumentResponse.model_validate(document)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{conversation_id}/documents",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_200_OK,
)
async def list_conversation_documents(
    conversation_id: UUID,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    manager: ConversationManager = Depends(get_conversation_manager),
    document_service: DocumentService = Depends(get_document_service),
) -> list[DocumentResponse]:
    """
    List all conversation-scoped documents for a specific conversation. Checks ownership.
    """
    user_id = UUID(user_context["user_id"])
    try:
        await manager._access_service.verify_owner(conversation_id, user_id)
        docs = await document_service.list_documents_by_conversation(
            conversation_id, user_id
        )
        from app.documents.domain.models import DocumentScope

        return [
            DocumentResponse.model_validate(d)
            for d in docs
            if d.scope == DocumentScope.CONVERSATION
        ]
    except ConversationNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedConversationAccessException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
