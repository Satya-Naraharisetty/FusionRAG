import logging
import pathlib
import re
from typing import Any
from uuid import UUID

from app.auth.domain.interfaces import TimeProvider, UnitOfWork, UUIDGenerator
from app.documents.domain.exceptions import (
    DocumentCorrupted,
    DocumentNotFound,
    DocumentTooLarge,
    DuplicateDocumentException,
    UnauthorizedDocumentAccess,
    UnsupportedDocumentType,
)
from app.documents.domain.interfaces import (
    ChecksumGenerator,
    DocumentRepository,
    IndexCache,
    StorageProvider,
    TaskQueue,
)
from app.documents.domain.models import Document, DocumentScope, DocumentStatus
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        storage_provider: StorageProvider,
        extractor_factory: ExtractorFactory,
        checksum_generator: ChecksumGenerator,
        task_queue: TaskQueue,
        document_processing_service: DocumentProcessingService,
        embedding_service: EmbeddingService,
        uow: UnitOfWork,
        uuid_generator: UUIDGenerator,
        time_provider: TimeProvider,
        max_upload_size: int,
        index_cache: IndexCache | None = None,
        malware_scanner: Any = None,
    ) -> None:
        self._document_repo = document_repo
        self._storage_provider = storage_provider
        self._extractor_factory = extractor_factory
        self._checksum_generator = checksum_generator
        self._task_queue = task_queue
        self._document_processing_service = document_processing_service
        self._embedding_service = embedding_service
        self._uow = uow
        self._uuid_generator = uuid_generator
        self._time_provider = time_provider
        self._max_upload_size = max_upload_size
        self._index_cache = index_cache
        self._malware_scanner = malware_scanner

    async def upload_document(
        self,
        original_filename: str,
        content_type: str,
        file_bytes: bytes,
        user_id: UUID,
        scope: DocumentScope = DocumentScope.LIBRARY,
        conversation_id: UUID | None = None,
    ) -> Document:
        """
        Validates, registers, and triggers the ingestion pipeline for a new document.
        """
        if scope == DocumentScope.LIBRARY:
            if conversation_id is not None:
                raise ValueError(
                    "Library-scoped documents must not have a conversation_id."
                )
        elif scope == DocumentScope.CONVERSATION:
            if conversation_id is None:
                raise ValueError(
                    "Conversation-scoped documents must have a conversation_id."
                )
        # 1. Reject empty files
        if not file_bytes or len(file_bytes) == 0:
            raise DocumentCorrupted("Uploaded file is empty.")

        # 2. Validate file size
        if len(file_bytes) > self._max_upload_size:
            raise DocumentTooLarge(
                f"File size {len(file_bytes)} exceeds maximum limit {self._max_upload_size}."
            )

        # 3. Sanitize filename
        safe_original_name = self._sanitize_filename(original_filename)

        # 4. Validate MIME and extension support
        try:
            self._extractor_factory.get_extractor(content_type, safe_original_name)
        except UnsupportedDocumentType:
            raise
        except Exception as e:
            raise UnsupportedDocumentType(f"Validation failed: {e}") from e

        # 4b. Scan for malware if scanner is present
        if self._malware_scanner:
            import os
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(file_bytes)
                tmp_path = tmp_file.name

            try:
                is_clean = await self._malware_scanner.scan(tmp_path)
                if not is_clean:
                    raise DocumentCorrupted(
                        f"Malware or virus signature detected in file: {safe_original_name}"
                    )
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        # 5. Generate checksum & check for duplicate for THIS user
        checksum = self._checksum_generator.generate(file_bytes)
        existing = self._document_repo.get_by_checksum_and_user(checksum, user_id)
        if existing:
            raise DuplicateDocumentException(
                f"A document with identical content already exists in your library (ID: {existing.id})."
            )

        # 6. Generate UUID & save to storage
        document_id = self._uuid_generator.generate()
        storage_key = self._storage_provider.save(
            filename=safe_original_name,
            content=file_bytes,
            user_id=user_id,
            document_id=document_id,
        )

        # 7. Create DB record as QUEUED
        now = self._time_provider.get_now()
        document = Document(
            id=document_id,
            user_id=user_id,
            scope=scope,
            conversation_id=conversation_id,
            filename=storage_key,
            original_filename=safe_original_name,
            content_type=content_type,
            file_size=len(file_bytes),
            checksum=checksum,
            status=DocumentStatus.QUEUED,
            extractor_version="v1",
            failure_reason=None,
            page_count=None,
            word_count=None,
            language=None,
            created_at=now,
            updated_at=now,
            processing_started_at=None,
            processing_completed_at=None,
        )

        try:
            saved_doc = self._document_repo.save(document)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            # Clean up the file from storage if DB write fails
            self._storage_provider.delete(storage_key)
            raise

        # 8. Trigger asynchronous processing task
        self._task_queue.enqueue(
            self._document_processing_service.process_document, saved_doc.id
        )

        return saved_doc

    def list_documents(self, user_id: UUID) -> list[Document]:
        """
        Lists the user's GLOBAL documents — the ones uploaded from the Documents
        section (``conversation_id`` is NULL). Chat-scoped documents belong to
        their conversation only and must never surface in the shared library,
        so they are excluded here. They are reachable via
        ``list_documents_by_conversation`` and ``get_document_by_id``.
        """
        return [
            doc
            for doc in self._document_repo.list_by_user(user_id)
            if doc.scope == DocumentScope.LIBRARY
        ]

    def list_documents_by_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> list[Document]:
        """
        Lists all documents belonging to a conversation.
        """
        return self._document_repo.list_by_conversation(conversation_id, user_id)

    def get_document_by_id(self, id: UUID, user_id: UUID) -> Document:
        """
        Retrieves a document. Validates existence and ownership.
        """
        document = self._document_repo.get_by_id(id)
        if not document:
            raise DocumentNotFound(f"Document with ID {id} not found.")

        if document.user_id != user_id:
            raise UnauthorizedDocumentAccess(
                "You do not have permission to access this document."
            )

        return document

    def delete_document(self, id: UUID, user_id: UUID) -> None:
        """
        Deletes the document database record first (source of truth) and then deletes the storage file.
        """
        # Verify document exists and belongs to the user
        document = self.get_document_by_id(id, user_id)

        try:
            # Delete DB record (will cascade delete chunks and document_embeddings in PostgreSQL)
            self._document_repo.delete(id)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

        # Clean up vectors from the vector store after PostgreSQL commit is successful
        try:
            self._embedding_service.delete_embeddings(document.id)
        except Exception as e:
            logger.error(
                f"Failed to delete Qdrant vectors during document deletion {document.id}: {e}"
            )

        # Invalidate index cache for user
        if self._index_cache:
            try:
                self._index_cache.invalidate(user_id)
            except Exception as e:
                logger.error(
                    f"Failed to invalidate index cache for user {user_id}: {e}"
                )

        # Attempt storage deletion (failures are logged, not raised)
        self._storage_provider.delete(document.filename)

    def delete_documents_by_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> int:
        """
        Deletes all documents belonging to a conversation.
        Returns the count of deleted documents.
        """
        documents = self._document_repo.list_by_conversation(conversation_id, user_id)
        conversation_docs = [
            d for d in documents if d.scope == DocumentScope.CONVERSATION
        ]
        count = 0
        for doc in conversation_docs:
            try:
                self.delete_document(doc.id, user_id)
                count += 1
            except Exception as e:
                logger.error(
                    f"Failed to delete document {doc.id} for conversation {conversation_id}: {e}"
                )
        return count

    def reprocess_document(self, id: UUID, user_id: UUID) -> Document:
        """
        Triggers reprocessing for a document by resetting its status to QUEUED.
        """
        # Fetch and verify ownership with row locking
        try:
            document = self._document_repo.get_by_id_for_update(id)
            if not document:
                raise DocumentNotFound(f"Document with ID {id} not found.")

            if document.user_id != user_id:
                raise UnauthorizedDocumentAccess(
                    "You do not have permission to reprocess this document."
                )

            # State transition check and update status
            document.transition_to(DocumentStatus.QUEUED)
            document.failure_reason = None
            document.processing_started_at = None
            document.processing_completed_at = None
            document.updated_at = self._time_provider.get_now()

            saved_doc = self._document_repo.save(document)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

        # Enqueue processing task
        self._task_queue.enqueue(
            self._document_processing_service.process_document, saved_doc.id
        )

        return saved_doc

    def _sanitize_filename(self, filename: str) -> str:
        """
        Strips folder paths and illegal path traversal characters from filename.
        """
        base = pathlib.Path(filename).name
        cleaned = re.sub(r"[^\w\.\-]", "_", base)
        if not cleaned or cleaned in (".", ".."):
            cleaned = "unnamed_file"
        return cleaned


class DocumentCorruptedError(UnsupportedDocumentType):
    """Raised when the uploaded file is zero-byte / empty."""

    pass
