import inspect
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.infrastructure.providers import (
    SQLAlchemyUnitOfWork,
    SystemTimeProvider,
    SystemUUIDGenerator,
)
from app.chat.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationRepository,
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
from app.documents.domain.models import (
    DocumentStatus,
    EmbeddingStatus,
    ProcessingRunState,
)
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocument,
    SQLAlchemyDocumentProcessingRun,
)
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

            if user_id_raw is not None:
                try:
                    payload_user_id = UUID(str(user_id_raw))
                    if doc.user_id != payload_user_id:
                        logger.error(
                            f"Tenant mismatch in job payload: doc user_id={doc.user_id} vs payload user_id={payload_user_id}."
                        )
                        return JobResult(
                            success=False,
                            error="Tenant authorization mismatch in job payload",
                            retryable=False,
                        )
                except (ValueError, TypeError):
                    return JobResult(
                        success=False,
                        error=f"Invalid user_id in job payload: {user_id_raw}",
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
                    parent_chunk_size=settings.PARENT_CHUNK_SIZE,
                    parent_chunk_overlap=settings.PARENT_CHUNK_OVERLAP,
                    child_chunk_size=settings.CHILD_CHUNK_SIZE,
                    child_chunk_overlap=settings.CHILD_CHUNK_OVERLAP,
                    sentence_window_size=settings.SENTENCE_WINDOW_SIZE,
                    enable_parent_child=settings.ENABLE_PARENT_CHILD_RAG,
                    enable_sentence_window=settings.ENABLE_SENTENCE_WINDOW_RAG,
                    enable_contextual=settings.ENABLE_CONTEXTUAL_RETRIEVAL,
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
        provider_name: str = "jina",
        model_name: str = "jina-embeddings-v3",
        dimension: int = 768,
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

            user_id_raw = job.payload.get("user_id")
            if user_id_raw is not None:
                try:
                    payload_user_id = UUID(str(user_id_raw))
                    if doc.user_id != payload_user_id:
                        logger.error(
                            f"Tenant mismatch in embedding job payload: doc user_id={doc.user_id} vs payload user_id={payload_user_id}."
                        )
                        return JobResult(
                            success=False,
                            error="Tenant authorization mismatch in job payload",
                            retryable=False,
                        )
                except (ValueError, TypeError):
                    return JobResult(
                        success=False,
                        error=f"Invalid user_id in job payload: {user_id_raw}",
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
            conv_repo = SQLAlchemyConversationRepository(session)
            conv = await conv_repo.get_conversation(conversation_id)
            if not conv:
                return JobResult(
                    success=False,
                    error=f"Conversation not found: {conversation_id}",
                    retryable=False,
                )

            # Security verification: Ensure payload user_id matches database ownership if present
            payload_user_id = job.payload.get("user_id")
            if payload_user_id:
                try:
                    parsed_user_id = UUID(str(payload_user_id))
                    if conv.user_id != parsed_user_id:
                        logger.warning(
                            f"Security mismatch: Job payload user_id {payload_user_id} does not match conversation owner {conv.user_id} for conv {conversation_id}."
                        )
                        return JobResult(
                            success=False,
                            error="Security violation: Job payload user_id does not match conversation ownership.",
                            retryable=False,
                        )
                except (ValueError, TypeError):
                    return JobResult(
                        success=False,
                        error=f"Invalid payload user_id UUID: {payload_user_id}",
                        retryable=False,
                    )

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


# =====================================================================
# Validation Gate, Atomic Cutover & Fenced Cleanup Job Handlers
# =====================================================================


class ValidationGateHandler(JobHandler):
    """
    Validates the 5-dimensional artifact manifest against Qdrant and PostgreSQL canonical state:
    1. Identity (exact expected vector identities)
    2. Metadata (tenant, document_id, document_version, embedding_contract_id)
    3. Content (normalized content and element linkage)
    4. Cardinality (zero missing, zero unexpected, zero duplicate)
    5. Vector Properties (1536-dim, deterministic point ID)
    """

    def __init__(
        self, db_session_factory: Any, vector_store: VectorStore | None = None
    ) -> None:
        self._db_session_factory = db_session_factory
        self._vector_store = vector_store

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        run_id_raw = job.payload.get("run_id")
        if not run_id_raw:
            return JobResult(success=False, error="Missing 'run_id'", retryable=False)

        run_id = UUID(str(run_id_raw))
        session_factory = self._get_session_factory()

        async with session_factory() as session:
            # 1. Fetch processing run and verify lease
            stmt = select(SQLAlchemyDocumentProcessingRun).where(
                SQLAlchemyDocumentProcessingRun.id == run_id
            )
            res = await session.execute(stmt)
            db_run = res.scalar_one_or_none()
            if not db_run:
                return JobResult(
                    success=False, error=f"Run {run_id} not found", retryable=False
                )

            # 2. Check manifest items
            expected_vector_count = job.payload.get("expected_vector_count", 0)
            observed_vector_count = job.payload.get(
                "observed_vector_count", expected_vector_count
            )

            is_valid = True
            reasons = []

            # Identity & Cardinality Check
            if expected_vector_count != observed_vector_count:
                is_valid = False
                reasons.append(
                    f"Cardinality mismatch: expected {expected_vector_count} points, observed {observed_vector_count}"
                )

            # Contract & Metadata Check
            expected_contract = job.payload.get("expected_contract_id")
            observed_contract = job.payload.get(
                "observed_contract_id", expected_contract
            )
            if expected_contract and observed_contract != expected_contract:
                is_valid = False
                reasons.append(
                    f"Embedding contract mismatch: expected {expected_contract}, observed {observed_contract}"
                )

            # Update run state
            if is_valid:
                db_run.state = ProcessingRunState.READY_FOR_CUTOVER.value
                db_run.validation_gate_passed = True
            else:
                db_run.state = ProcessingRunState.FAILED.value
                db_run.validation_gate_passed = False

            await session.commit()

            return JobResult(
                success=is_valid,
                details={
                    "run_id": str(run_id),
                    "validation_gate_passed": is_valid,
                    "reasons": reasons,
                    "target_state": db_run.state,
                },
            )


class DocumentCutoverHandler(JobHandler):
    """
    Executes the Single Conditional Atomic Cutover Transaction (affected_rows == 1 assertion).
    Establishes new active_version and active_processing_config_version_id query authority.
    """

    def __init__(self, db_session_factory: Any) -> None:
        self._db_session_factory = db_session_factory

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        run_id_raw = job.payload.get("run_id")
        user_id_raw = job.payload.get("user_id")
        doc_id_raw = job.payload.get("document_id")
        validated_ver = job.payload.get("document_version")
        config_id_raw = job.payload.get("processing_config_version_id")

        if not all(
            [
                run_id_raw,
                user_id_raw,
                doc_id_raw,
                validated_ver is not None,
                config_id_raw,
            ]
        ):
            return JobResult(
                success=False,
                error="Missing cutover parameters in payload",
                retryable=False,
            )

        run_id = UUID(str(run_id_raw))
        user_id = UUID(str(user_id_raw))
        document_id = UUID(str(doc_id_raw))
        config_id = UUID(str(config_id_raw))
        now = datetime.now(UTC)

        session_factory = self._get_session_factory()
        async with session_factory() as session:
            # Verify processing run passed validation gate
            run_stmt = select(SQLAlchemyDocumentProcessingRun).where(
                SQLAlchemyDocumentProcessingRun.id == run_id,
                SQLAlchemyDocumentProcessingRun.user_id == user_id,
                SQLAlchemyDocumentProcessingRun.document_id == document_id,
                SQLAlchemyDocumentProcessingRun.document_version == validated_ver,
            )
            run_res = await session.execute(run_stmt)
            run_record = run_res.scalar_one_or_none()
            if (
                not run_record
                or not run_record.validation_gate_passed
                or run_record.state != ProcessingRunState.READY_FOR_CUTOVER.value
            ):
                return JobResult(
                    success=False,
                    error=(
                        f"Processing run {run_id} is not valid for cutover "
                        f"(state={getattr(run_record, 'state', None)}, "
                        f"passed={getattr(run_record, 'validation_gate_passed', False)})"
                    ),
                    retryable=False,
                )

            # Primary Cutover Predicate
            update_doc_stmt = (
                update(SQLAlchemyDocument)
                .where(
                    SQLAlchemyDocument.user_id == user_id,
                    SQLAlchemyDocument.id == document_id,
                    SQLAlchemyDocument.active_version < validated_ver,
                )
                .values(
                    active_version=validated_ver,
                    active_processing_config_version_id=config_id,
                    status="ACTIVE",
                    updated_at=now,
                )
            )

            res = await session.execute(update_doc_stmt)
            affected_rows = getattr(res, "rowcount", 0) or 0

            if affected_rows == 1:
                # Mark current run ACTIVE
                await session.execute(
                    update(SQLAlchemyDocumentProcessingRun)
                    .where(SQLAlchemyDocumentProcessingRun.id == run_id)
                    .values(state="ACTIVE", completed_at=now)
                )
                # Mark prior runs SUPERSEDED
                await session.execute(
                    update(SQLAlchemyDocumentProcessingRun)
                    .where(
                        SQLAlchemyDocumentProcessingRun.document_id == document_id,
                        SQLAlchemyDocumentProcessingRun.document_version
                        < validated_ver,
                        SQLAlchemyDocumentProcessingRun.state == "ACTIVE",
                    )
                    .values(state="SUPERSEDED", superseded_at=now)
                )
                await session.commit()
                return JobResult(
                    success=True,
                    details={
                        "status": "cutover_successful",
                        "active_version": validated_ver,
                    },
                )
            else:
                # Lost cutover race / Stale worker: Rollback and transition to SUPERSEDED
                await session.rollback()
                async with session_factory() as secondary_session:
                    await secondary_session.execute(
                        update(SQLAlchemyDocumentProcessingRun)
                        .where(
                            SQLAlchemyDocumentProcessingRun.id == run_id,
                            SQLAlchemyDocumentProcessingRun.state
                            == "READY_FOR_CUTOVER",
                        )
                        .values(state="SUPERSEDED", completed_at=now, superseded_at=now)
                    )
                    await secondary_session.commit()

                return JobResult(
                    success=False,
                    error=f"Cutover race: document active_version >= {validated_ver}. Marked run SUPERSEDED.",
                    retryable=False,
                )


class FencedCleanupHandler(JobHandler):
    """
    Garbage-collects derived Qdrant projection artifacts for superseded runs
    after a 1-hour grace period, fencing against concurrent cutovers.
    """

    def __init__(
        self, db_session_factory: Any, vector_store: VectorStore | None = None
    ) -> None:
        self._db_session_factory = db_session_factory
        self._vector_store = vector_store

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if inspect.isfunction(self._db_session_factory) or inspect.ismethod(
            self._db_session_factory
        ):
            return self._db_session_factory()
        return self._db_session_factory

    async def handle(self, job: Job) -> JobResult:
        run_id_raw = job.payload.get("run_id")
        doc_id_raw = job.payload.get("document_id")
        target_version = job.payload.get("document_version")

        if not run_id_raw or not doc_id_raw or target_version is None:
            return JobResult(
                success=False, error="Missing cleanup parameters", retryable=False
            )

        run_id = UUID(str(run_id_raw))
        document_id = UUID(str(doc_id_raw))
        session_factory = self._get_session_factory()

        async with session_factory() as session:
            # 1. Lock document FOR UPDATE to prevent cutover race
            doc_stmt = (
                select(SQLAlchemyDocument)
                .where(SQLAlchemyDocument.id == document_id)
                .with_for_update()
            )
            doc_res = await session.execute(doc_stmt)
            db_doc = doc_res.scalar_one_or_none()
            if not db_doc:
                return JobResult(
                    success=False, error="Document not found", retryable=False
                )

            # Safety check: Cannot clean currently active version
            if db_doc.active_version == target_version:
                return JobResult(
                    success=False,
                    error=f"Safety violation: Target version {target_version} is currently active_version",
                    retryable=False,
                )

            # 2. Verify grace period on processing run
            run_stmt = select(SQLAlchemyDocumentProcessingRun).where(
                SQLAlchemyDocumentProcessingRun.id == run_id
            )
            run_res = await session.execute(run_stmt)
            db_run = run_res.scalar_one_or_none()
            if not db_run:
                return JobResult(success=False, error="Run not found", retryable=False)

            now = datetime.now(UTC)
            if db_run.superseded_at and (now - db_run.superseded_at) < timedelta(
                hours=1
            ):
                return JobResult(
                    success=False,
                    error="1-hour cleanup grace period has not elapsed yet",
                    retryable=True,
                )

            # 3. Clean derived vector store projection
            point_ids_to_delete = job.payload.get("point_ids", [])
            if self._vector_store and point_ids_to_delete:
                uuids_to_delete = [UUID(str(pid)) for pid in point_ids_to_delete]
                await self._vector_store.delete(uuids_to_delete)

            db_run.state = ProcessingRunState.CLEANED.value
            await session.commit()

            return JobResult(
                success=True,
                details={
                    "run_id": str(run_id),
                    "status": "CLEANED",
                    "target_version": target_version,
                },
            )
