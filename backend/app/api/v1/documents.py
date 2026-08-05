from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import (
    get_current_user_context,
    get_document_service,
    get_embedding_service,
)
from app.documents.domain.models import EmbeddingStatus
from app.documents.infrastructure.tasks import FastAPIBackgroundTasksQueue
from app.documents.services.document_service import DocumentService
from app.documents.services.embedding_service import EmbeddingService

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
    document = await document_service.upload_document(
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


class EmbeddingStatusResponse(BaseModel):
    status: str
    chunks_total: int
    embedded_chunks: int
    failed_chunks: int
    provider: str
    model: str


@router.post("/{id}/embeddings/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_embeddings(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Manually triggers complete regeneration of embeddings for a document.
    """
    user_id = UUID(current_user["user_id"])
    document = document_service.get_document_by_id(id, user_id)

    task_queue = FastAPIBackgroundTasksQueue(background_tasks)
    task_queue.enqueue(embedding_service.generate_embeddings, document.id, force=True)

    return {"message": "Embedding regeneration task queued successfully."}


@router.delete("/{id}/embeddings", status_code=status.HTTP_204_NO_CONTENT)
def delete_embeddings(
    id: UUID,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Deletes all embedding metadata and vector database entries for a document.
    """
    user_id = UUID(current_user["user_id"])
    document = document_service.get_document_by_id(id, user_id)

    embedding_service.delete_embeddings(document.id)
    return None


@router.get("/{id}/embeddings/status", response_model=EmbeddingStatusResponse)
def get_embeddings_status(
    id: UUID,
    current_user: dict = Depends(get_current_user_context),
    document_service: DocumentService = Depends(get_document_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """
    Retrieves the embedding generation status and counts for a document.
    """
    user_id = UUID(current_user["user_id"])
    document = document_service.get_document_by_id(id, user_id)

    chunks = embedding_service._chunk_repo.list_by_document(document.id)
    if not chunks:
        return EmbeddingStatusResponse(
            status=EmbeddingStatus.PENDING.value,
            chunks_total=0,
            embedded_chunks=0,
            failed_chunks=0,
            provider=embedding_service._provider_name,
            model=embedding_service._model_name,
        )

    embeddings = embedding_service._embedding_repo.list_by_document(document.id)
    existing_map = {emb.chunk_id: emb for emb in embeddings}

    chunks_total = len(chunks)
    embedded_chunks = sum(
        1
        for c in chunks
        if c.id in existing_map
        and existing_map[c.id].status == EmbeddingStatus.COMPLETED
    )
    failed_chunks = sum(
        1
        for c in chunks
        if c.id in existing_map and existing_map[c.id].status == EmbeddingStatus.FAILED
    )
    generating_chunks = sum(
        1
        for c in chunks
        if c.id in existing_map
        and existing_map[c.id].status == EmbeddingStatus.GENERATING
    )

    if failed_chunks > 0:
        overall_status = EmbeddingStatus.FAILED.value
    elif generating_chunks > 0:
        overall_status = EmbeddingStatus.GENERATING.value
    elif embedded_chunks == chunks_total:
        overall_status = EmbeddingStatus.COMPLETED.value
    else:
        overall_status = EmbeddingStatus.PENDING.value

    return EmbeddingStatusResponse(
        status=overall_status,
        chunks_total=chunks_total,
        embedded_chunks=embedded_chunks,
        failed_chunks=failed_chunks,
        provider=embedding_service._provider_name,
        model=embedding_service._model_name,
    )
