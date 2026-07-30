from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import get_current_user_context, get_document_service
from app.documents.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


class DocumentResponse(BaseModel):
    id: UUID
    user_id: UUID
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    checksum: str
    status: str
    extractor_version: str
    failure_reason: str | None = None
    page_count: int | None = None
    word_count: int | None = None
    language: str | None = None
    created_at: datetime
    updated_at: datetime
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    Upload a document, validating the formats and enqueuing background parsing & chunking.
    """
    user_id = UUID(current_user["user_id"])
    file_bytes = await file.read()

    # Delegate orchestration to DocumentService
    document = document_service.upload_document(
        original_filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
        user_id=user_id,
    )
    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    List uploaded documents for the currently authenticated user.
    """
    user_id = UUID(current_user["user_id"])
    return document_service.list_documents(user_id)


@router.get("/{id}", response_model=DocumentResponse)
def get_document(
    id: UUID,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    Retrieve details of a single document by UUID. Enforces owner authorization.
    """
    user_id = UUID(current_user["user_id"])
    return document_service.get_document_by_id(id, user_id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    id: UUID,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    Deletes a document and all its chunks from the repository and storage.
    """
    user_id = UUID(current_user["user_id"])
    document_service.delete_document(id, user_id)
    return None


@router.post("/{id}/reprocess", response_model=DocumentResponse)
def reprocess_document(
    id: UUID,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    Manually triggers reprocessing of a document.
    """
    user_id = UUID(current_user["user_id"])
    return document_service.reprocess_document(id, user_id)
