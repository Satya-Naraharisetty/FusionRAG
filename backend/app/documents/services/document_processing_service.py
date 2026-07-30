import logging
from uuid import UUID

from app.auth.domain.interfaces import TimeProvider, UnitOfWork
from app.documents.domain.interfaces import (
    ChunkRepository,
    DocumentRepository,
    StorageProvider,
)
from app.documents.domain.models import DocumentStatus
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.services.chunking import ChunkingService
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
        storage_provider: StorageProvider,
        extractor_factory: ExtractorFactory,
        text_cleaner: TextCleaner,
        metadata_extractor: MetadataExtractor,
        chunking_service: ChunkingService,
        uow: UnitOfWork,
        time_provider: TimeProvider,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._storage_provider = storage_provider
        self._extractor_factory = extractor_factory
        self._text_cleaner = text_cleaner
        self._metadata_extractor = metadata_extractor
        self._chunking_service = chunking_service
        self._uow = uow
        self._time_provider = time_provider

    def process_document(self, document_id: UUID) -> None:
        """
        Coordinates the ingestion pipeline end-to-end for a given document.
        Enforces locking and database transaction boundaries.
        """
        logger.info(f"Starting background processing for document {document_id}")

        # 1. Fetch document and lock row to initialize processing state
        try:
            document = self._document_repo.get_by_id_for_update(document_id)
            if not document:
                logger.error(f"Document {document_id} not found for processing.")
                return

            # Concurrency Guard: If it's already PROCESSING, exit immediately.
            if document.status == DocumentStatus.PROCESSING:
                logger.warning(
                    f"Document {document_id} is already in PROCESSING state. Exiting concurrent task run."
                )
                return

            # Enforce valid transition and update status
            document.transition_to(DocumentStatus.PROCESSING)
            document.processing_started_at = self._time_provider.get_now()
            document.failure_reason = None
            document.updated_at = self._time_provider.get_now()
            self._document_repo.save(document)
            self._uow.commit()
        except Exception as e:
            self._uow.rollback()
            logger.exception(
                f"Failed to transition document {document_id} to PROCESSING: {e}"
            )
            return

        # 2. Execute extraction, cleaning, metadata gathering, and chunking
        try:
            file_bytes = self._storage_provider.get(document.filename)

            # Retrieve strategy class
            extractor = self._extractor_factory.get_extractor(
                document.content_type, document.original_filename
            )

            # Extraction
            extraction_result = extractor.extract(file_bytes)

            # Text cleaning
            cleaned_text = self._text_cleaner.clean(extraction_result.text)

            # Metadata extraction
            metadata = self._metadata_extractor.extract_metadata(
                cleaned_text, extraction_result.page_count
            )

            # Chunk generation
            chunk_result = self._chunking_service.chunk_document(
                cleaned_text, document.id
            )

            # 3. Batch commit results (idempotent: delete previous chunks first)
            document = self._document_repo.get_by_id_for_update(document_id)
            if not document:
                raise RuntimeError("Document was deleted during pipeline execution.")

            # Delete previous chunks first (in the same transaction)
            self._chunk_repo.delete_by_document(document.id)

            # Save the new chunks
            self._chunk_repo.save_bulk(chunk_result.chunks)

            # Enforce valid transition and update status/metadata
            document.transition_to(DocumentStatus.COMPLETED)
            document.page_count = metadata.page_count
            document.word_count = metadata.word_count
            document.language = metadata.language
            document.processing_completed_at = self._time_provider.get_now()
            document.updated_at = self._time_provider.get_now()
            self._document_repo.save(document)

            self._uow.commit()
            logger.info(f"Ingestion completed successfully for document {document_id}")

        except Exception as e:
            self._uow.rollback()
            logger.exception(
                f"Ingestion pipeline execution failed for document {document_id}: {e}"
            )

            # Transition document state to FAILED
            try:
                document = self._document_repo.get_by_id_for_update(document_id)
                if document:
                    document.transition_to(DocumentStatus.FAILED)
                    document.failure_reason = str(e)
                    document.processing_completed_at = self._time_provider.get_now()
                    document.updated_at = self._time_provider.get_now()
                    self._document_repo.save(document)
                    self._uow.commit()
            except Exception as fe:
                self._uow.rollback()
                logger.critical(
                    f"Failed to record FAILED status for document {document_id}: {fe}"
                )
