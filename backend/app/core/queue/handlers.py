import inspect
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.infrastructure.providers import (
    SQLAlchemyUnitOfWork,
    SystemTimeProvider,
    SystemUUIDGenerator,
)
from app.chat.infrastructure.persistence.repositories.message_repository import (
    SQLAlchemyMessageRepository,
)
from app.chat.infrastructure.persistence.repositories.summary_repository import (
    SQLAlchemySummaryRepository,
)
from app.chat.services.conversation_summarizer import LLMConversationSummarizer
from app.core.config import settings
from app.core.queue.interfaces import Job, JobHandler, JobResult
from app.documents.domain.exceptions import (
    DocumentCorrupted,
    DocumentExtractionFailed,
    DocumentNotFound,
    UnsupportedDocumentType,
)
from app.documents.domain.interfaces import (
    EmbeddingGenerator,
    StorageProvider,
    VectorStore,
)
from app.documents.domain.models import DocumentStatus, EmbeddingStatus
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.infrastructure.persistence.repositories.document_repository import (
    SQLAlchemyDocumentRepository,
)
from app.documents.infrastructure.persistence.repositories.embedding_repository import (
    SQLAlchemyEmbeddingRepository,
)
from app.documents.services.chunking import ChunkingService
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.embedding_service import EmbeddingService
from app.documents.services.index_cache import IndexCache
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner

logger = logging.getLogger(__name__)


class ProcessDocumentJobHandler(JobHandler):
    """
    Handles 'PROCESS_DOCUMENT' durable background jobs.
    Performs extraction, chunking, and persistence.
    """

    def __init__(
        self,
        db_session_factory: Any,
        storage_provider: StorageProvider | None = None,
        extractor_factory: ExtractorFactory | None = None,
        task_queue: Any = None,
        index_cache: IndexCache | None = None,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._storage_provider = storage_provider
        self._extractor_factory = extractor_factory
        self._task_queue = task_queue
        self._index_cache = index_cache

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        doc_id_raw = job.payload.get("document_id")
        if not doc_id_raw:
            return JobResult(
                success=False,
                error="Missing 'document_id' in job payload",
                retryable=False,
            )

        try:
            document_id = UUID(str(doc_id_raw))
        except (ValueError, TypeError):
            return JobResult(
                success=False,
                error=f"Invalid UUID in job payload: {doc_id_raw}",
                retryable=False,
            )

        user_id_raw = job.payload.get("user_id")

        session_factory = self._get_session_factory()
        async with session_factory() as session:
            doc_repo = SQLAlchemyDocumentRepository(session)
            doc = await doc_repo.get_by_id(document_id)
            if not doc:
                logger.warning(
                    f"Document {document_id} not found during background processing. Aborting non-retryable."
                )
                return JobResult(
                    success=False,
                    error=f"Document {document_id} not found",
                    retryable=False,
                )

            if doc.status == DocumentStatus.COMPLETED:
                # Downstream verification: verify that all expected chunks have completed embeddings
                chunk_repo = SQLAlchemyChunkRepository(session)
                embedding_repo = SQLAlchemyEmbeddingRepository(session)

                chunks = await chunk_repo.list_by_document(document_id)
                if not chunks:
                    logger.warning(
                        f"Document {document_id} marked COMPLETED but has 0 chunks. Inconsistent state, triggering retry."
                    )
                    return JobResult(
                        success=False,
                        error=f"Document {document_id} marked COMPLETED but has 0 chunks",
                        retryable=True,
                    )

                chunk_ids = [c.id for c in chunks]
                embeddings = await embedding_repo.get_by_chunk_ids(chunk_ids)
                emb_map = {e.chunk_id: e for e in embeddings}

                # Check: every expected chunk must have exactly one COMPLETED embedding
                all_completed = len(embeddings) == len(chunks) and all(
                    emb_map.get(cid) is not None
                    and emb_map[cid].status == EmbeddingStatus.COMPLETED
                    for cid in chunk_ids
                )

                if all_completed:
                    logger.info(
                        f"Document {document_id} already COMPLETED with all {len(chunks)} embeddings verified. Idempotent skip."
                    )
                    return JobResult(
                        success=True,
                        details={
                            "status": "already_completed",
                            "embeddings": "verified_complete",
                            "document_id": str(document_id),
                        },
                    )

                logger.info(
                    f"Document {document_id} is COMPLETED but has incomplete embeddings ({len(embeddings)}/{len(chunks)} recorded). Enqueueing GENERATE_EMBEDDINGS."
                )
                if self._task_queue is not None:
                    try:
                        await self._task_queue.enqueue(
                            task_type="GENERATE_EMBEDDINGS",
                            payload={
                                "document_id": str(document_id),
                                "user_id": str(user_id_raw) if user_id_raw else None,
                            },
                            max_attempts=3,
                        )
                        return JobResult(
                            success=True,
                            details={
                                "status": "already_completed",
                                "embeddings": "enqueued",
                                "document_id": str(document_id),
                            },
                        )
                    except Exception as enq_err:
                        logger.error(
                            f"Failed to enqueue downstream GENERATE_EMBEDDINGS for completed document {document_id}: {enq_err}"
                        )
                        return JobResult(
                            success=False,
                            error=f"Failed to enqueue downstream GENERATE_EMBEDDINGS: {enq_err}",
                            retryable=True,
                        )
                return JobResult(
                    success=True,
                    details={
                        "status": "already_completed",
                        "document_id": str(document_id),
                    },
                )

            storage = self._storage_provider
            if storage is None:
                from app.api.dependencies import get_storage_provider

                storage = get_storage_provider(session)

            extractor_factory = self._extractor_factory or ExtractorFactory()

            processing_service = DocumentProcessingService(
                document_repo=doc_repo,
                chunk_repo=SQLAlchemyChunkRepository(session),
                storage_provider=storage,
                extractor_factory=extractor_factory,
                text_cleaner=TextCleaner(),
                metadata_extractor=MetadataExtractor(),
                chunking_service=ChunkingService(
                    chunk_size=settings.CHUNK_SIZE,
                    chunk_overlap=settings.CHUNK_OVERLAP,
                    min_chunk_size=settings.MIN_CHUNK_SIZE,
                    strategy=settings.CHUNK_STRATEGY,
                ),
                uow=SQLAlchemyUnitOfWork(session),
                time_provider=SystemTimeProvider(),
                event_dispatcher=None,
                index_cache=self._index_cache,
            )

            try:
                await processing_service.process_document(document_id)
            except (
                DocumentNotFound,
                DocumentCorrupted,
                UnsupportedDocumentType,
                DocumentExtractionFailed,
            ) as non_ret:
                logger.warning(
                    f"Non-retryable processing failure for document {document_id}: {non_ret}"
                )
                return JobResult(success=False, error=str(non_ret), retryable=False)
            except Exception as exc:
                logger.exception(
                    f"Transient error processing document {document_id}: {exc}"
                )
                return JobResult(success=False, error=str(exc), retryable=True)

        if self._task_queue is not None:
            try:
                await self._task_queue.enqueue(
                    task_type="GENERATE_EMBEDDINGS",
                    payload={
                        "document_id": str(document_id),
                        "user_id": str(user_id_raw) if user_id_raw else None,
                    },
                    max_attempts=3,
                )
            except Exception as enq_err:
                logger.error(
                    f"Failed to enqueue downstream GENERATE_EMBEDDINGS job: {enq_err}"
                )
                return JobResult(
                    success=False,
                    error=f"Failed to enqueue downstream GENERATE_EMBEDDINGS: {enq_err}",
                    retryable=True,
                    details={"document_id": str(document_id)},
                )

        return JobResult(
            success=True,
            details={"document_id": str(document_id)},
        )


class GenerateEmbeddingsJobHandler(JobHandler):
    """
    Handles 'GENERATE_EMBEDDINGS' durable background jobs.
    Invokes EmbeddingService to generate and upsert vector representations.
    """

    def __init__(
        self,
        db_session_factory: Any,
        embedding_generator: EmbeddingGenerator | Any | None = None,
        vector_store: VectorStore | Any | None = None,
        batch_size: int = 64,
        provider_name: str = "openai",
        model_name: str = "text-embedding-3-small",
        dimension: int = 1536,
        embedding_version: str = "v1",
    ) -> None:
        self._db_session_factory = db_session_factory
        self._embedding_generator = embedding_generator
        self._vector_store = vector_store
        self._batch_size = batch_size
        self._provider_name = provider_name
        self._model_name = model_name
        self._dimension = dimension
        self._embedding_version = embedding_version

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        doc_id_raw = job.payload.get("document_id")
        if not doc_id_raw:
            return JobResult(
                success=False,
                error="Missing 'document_id' in job payload",
                retryable=False,
            )

        try:
            document_id = UUID(str(doc_id_raw))
        except (ValueError, TypeError):
            return JobResult(
                success=False,
                error=f"Invalid UUID in job payload: {doc_id_raw}",
                retryable=False,
            )

        force = bool(job.payload.get("force", False))

        if inspect.isfunction(self._embedding_generator) or inspect.ismethod(
            self._embedding_generator
        ):
            generator = self._embedding_generator()
        elif self._embedding_generator is not None:
            generator = self._embedding_generator
        else:
            from app.api.dependencies import get_embedding_generator

            generator = get_embedding_generator()

        if inspect.isfunction(self._vector_store) or inspect.ismethod(
            self._vector_store
        ):
            store = self._vector_store()
        elif self._vector_store is not None:
            store = self._vector_store
        else:
            from app.api.dependencies import get_vector_store

            store = get_vector_store()

        session_factory = self._get_session_factory()
        async with session_factory() as session:
            doc_repo = SQLAlchemyDocumentRepository(session)
            doc = await doc_repo.get_by_id(document_id)
            if not doc:
                logger.warning(
                    f"Document {document_id} not found during embedding generation job. Aborting non-retryable."
                )
                return JobResult(
                    success=False,
                    error=f"Document {document_id} not found",
                    retryable=False,
                )

            embedding_service = EmbeddingService(
                embedding_generator=generator,
                vector_store=store,
                embedding_repo=SQLAlchemyEmbeddingRepository(session),
                chunk_repo=SQLAlchemyChunkRepository(session),
                document_repo=doc_repo,
                uow=SQLAlchemyUnitOfWork(session),
                time_provider=SystemTimeProvider(),
                uuid_generator=SystemUUIDGenerator(),
                batch_size=self._batch_size,
                provider_name=self._provider_name,
                model_name=self._model_name,
                dimension=self._dimension,
                embedding_version=self._embedding_version,
            )

            try:
                await embedding_service.generate_embeddings(document_id, force=force)
            except DocumentNotFound as dnf:
                logger.warning(
                    f"Document {document_id} not found in embedding service: {dnf}"
                )
                return JobResult(success=False, error=str(dnf), retryable=False)
            except Exception as exc:
                logger.exception(
                    f"Transient error generating embeddings for document {document_id}: {exc}"
                )
                return JobResult(success=False, error=str(exc), retryable=True)

            doc_chunks = await SQLAlchemyChunkRepository(session).list_by_document(
                document_id
            )
            if doc_chunks:
                embs = await SQLAlchemyEmbeddingRepository(session).get_by_chunk_ids(
                    [c.id for c in doc_chunks]
                )
                emb_map = {e.chunk_id: e for e in embs}
                uncompleted = [
                    c
                    for c in doc_chunks
                    if emb_map.get(c.id) is None
                    or emb_map[c.id].status != EmbeddingStatus.COMPLETED
                ]
                if uncompleted:
                    error_msg = f"Embedding generation incomplete: {len(uncompleted)}/{len(doc_chunks)} chunks not completed"
                    logger.warning(error_msg)
                    return JobResult(
                        success=False,
                        error=error_msg,
                        retryable=True,
                        details={
                            "document_id": str(document_id),
                            "uncompleted_count": len(uncompleted),
                        },
                    )

        return JobResult(
            success=True,
            details={"document_id": str(document_id)},
        )


class SummarizeConversationJobHandler(JobHandler):
    """
    Handles 'SUMMARIZE_CONVERSATION' durable background jobs.
    Performs rolling memory summarization for a conversation.
    """

    def __init__(
        self,
        db_session_factory: Any,
        llm_provider: Any = None,
        model: str = "gemini-2.5-flash",
        summary_trigger_messages: int = 10,
        max_messages_per_context: int = 5,
        summary_max_tokens: int = 500,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._llm_provider = llm_provider
        self._model = model
        self._summary_trigger_messages = summary_trigger_messages
        self._max_messages_per_context = max_messages_per_context
        self._summary_max_tokens = summary_max_tokens

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        conv_id_raw = job.payload.get("conversation_id")
        if not conv_id_raw:
            return JobResult(
                success=False,
                error="Missing 'conversation_id' in job payload",
                retryable=False,
            )

        try:
            conversation_id = UUID(str(conv_id_raw))
        except (ValueError, TypeError):
            return JobResult(
                success=False,
                error=f"Invalid conversation UUID: {conv_id_raw}",
                retryable=False,
            )

        if inspect.isfunction(self._llm_provider) or inspect.ismethod(
            self._llm_provider
        ):
            llm = self._llm_provider()
        elif self._llm_provider is not None:
            llm = self._llm_provider
        else:
            from app.api.dependencies import get_llm_provider

            llm = get_llm_provider()

        session_factory = self._get_session_factory()
        async with session_factory() as session:
            message_repo = SQLAlchemyMessageRepository(session)
            summary_repo = SQLAlchemySummaryRepository(session)

            count = await message_repo.count_messages(conversation_id)
            if count < self._summary_trigger_messages:
                return JobResult(
                    success=True,
                    details={"status": "skipped_count_below_threshold", "count": count},
                )

            summarizer = LLMConversationSummarizer(
                llm_provider=llm,
                summary_repo=summary_repo,
                message_repo=message_repo,
                model=self._model,
                summary_max_tokens=self._summary_max_tokens,
            )

            messages = await message_repo.get_recent_messages(
                conversation_id, limit=1000
            )
            up_to_idx = count - self._max_messages_per_context - 1
            if up_to_idx >= 0 and up_to_idx < len(messages):
                up_to_msg = messages[up_to_idx]
                try:
                    await summarizer.summarize(conversation_id, up_to_msg.id)
                    await session.commit()
                    return JobResult(
                        success=True,
                        details={
                            "status": "summarized",
                            "up_to_message_id": str(up_to_msg.id),
                        },
                    )
                except Exception as exc:
                    logger.exception(
                        f"Transient error summarizing conversation {conversation_id}: {exc}"
                    )
                    return JobResult(success=False, error=str(exc), retryable=True)

        return JobResult(
            success=True,
            details={"conversation_id": str(conversation_id), "status": "summarized"},
        )
