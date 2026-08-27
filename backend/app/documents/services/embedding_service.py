import logging
import time
from uuid import UUID

from app.auth.domain.interfaces import TimeProvider, UnitOfWork, UUIDGenerator
from app.documents.domain.exceptions import DocumentNotFound
from app.documents.domain.interfaces import (
    ChunkRepository,
    DocumentRepository,
    EmbeddingGenerator,
    EmbeddingRepository,
    VectorStore,
)
from app.documents.domain.models import (
    Embedding,
    EmbeddingMetadata,
    EmbeddingStateMachine,
    EmbeddingStatus,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service layer coordinating chunk embedding generation, vector database storage,
    relational metadata persistence, state machine validations, and failure boundaries.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        embedding_repo: EmbeddingRepository,
        chunk_repo: ChunkRepository,
        document_repo: DocumentRepository,
        uow: UnitOfWork,
        time_provider: TimeProvider,
        uuid_generator: UUIDGenerator,
        batch_size: int,
        provider_name: str,
        model_name: str,
        dimension: int,
        embedding_version: str,
    ) -> None:
        self._embedding_generator = embedding_generator
        self._vector_store = vector_store
        self._embedding_repo = embedding_repo
        self._chunk_repo = chunk_repo
        self._document_repo = document_repo
        self._uow = uow
        self._time_provider = time_provider
        self._uuid_generator = uuid_generator
        self._batch_size = batch_size
        self._provider_name = provider_name
        self._model_name = model_name
        self._dimension = dimension
        self._embedding_version = embedding_version

    async def generate_embeddings(self, document_id: UUID, force: bool = False) -> None:
        """
        Generates embeddings for chunks belonging to a document asynchronously.
        If force=True, deletes existing embeddings and vectors, and regenerates.
        Otherwise, only embeds chunks with FAILED, PENDING, or missing statuses.
        """
        logger.info(
            f"Initiating embedding generation for document {document_id} (force={force})"
        )

        document = await self._document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFound(f"Document with ID {document_id} not found.")

        doc_user_id = str(document.user_id)
        doc_scope = (
            document.scope.value
            if hasattr(document.scope, "value")
            else str(document.scope)
        )
        doc_conversation_id = (
            str(document.conversation_id) if document.conversation_id else None
        )
        doc_language = document.language or "en"

        chunks = await self._chunk_repo.list_by_document(document_id)
        if not chunks:
            logger.info(f"No chunks found for document {document_id}. Skipping.")
            return

        if force:
            logger.info(
                f"Regeneration requested: clearing existing database metadata and vectors for document {document_id}"
            )
            try:
                await self._embedding_repo.delete_by_document(document_id)
                await self._uow.commit()
                # Deleting from the vector store is done after DB commit is verified
                await self._vector_store.delete_document(document_id)
            except Exception as e:
                await self._uow.rollback()
                logger.exception(
                    f"Failed to clear old embeddings/vectors for document {document_id}: {e}"
                )
                raise

        # Retrieve current embedding records
        existing_embeddings = await self._embedding_repo.list_by_document(document_id)
        existing_map = {emb.chunk_id: emb for emb in existing_embeddings}

        # Filter chunks that need embedding
        chunks_to_embed = []
        for chunk in chunks:
            emb = existing_map.get(chunk.id)
            if not emb or emb.status != EmbeddingStatus.COMPLETED:
                chunks_to_embed.append(chunk)

        if not chunks_to_embed:
            logger.info(
                f"All chunks for document {document_id} already have COMPLETED embeddings."
            )
            return

        logger.info(
            f"Embedding {len(chunks_to_embed)} out of {len(chunks)} total chunks for document {document_id}"
        )

        # Batch chunks
        chunk_batches = [
            chunks_to_embed[i : i + self._batch_size]
            for i in range(0, len(chunks_to_embed), self._batch_size)
        ]

        for batch in chunk_batches:
            try:
                # 1. Update status to GENERATING in DB first
                now = self._time_provider.get_now()
                for chunk in batch:
                    old_emb = existing_map.get(chunk.id)
                    current_status = (
                        old_emb.status if old_emb else EmbeddingStatus.PENDING
                    )
                    EmbeddingStateMachine.validate_transition(
                        current_status, EmbeddingStatus.GENERATING
                    )

                    emb = Embedding(
                        id=old_emb.id if old_emb else self._uuid_generator.generate(),
                        chunk_id=chunk.id,
                        status=EmbeddingStatus.GENERATING,
                        metadata=EmbeddingMetadata(
                            provider=self._provider_name,
                            model=self._model_name,
                            dimension=self._dimension,
                            embedding_version=self._embedding_version,
                        ),
                        created_at=old_emb.created_at if old_emb else now,
                        updated_at=now,
                    )
                    await self._embedding_repo.save(emb)
                await self._uow.commit()

                from app.core.telemetry import (
                    EMBEDDING_CHUNKS,
                    INGESTION_STAGE_DURATION,
                    QDRANT_OPERATION_DURATION,
                    get_tracer,
                )

                tracer = get_tracer("hybrid-rag.embedding")

                # 2. Call embedding generator
                texts = [
                    c.metadata.get("contextual_text", c.text)
                    if isinstance(c.metadata, dict)
                    else c.text
                    for c in batch
                ]
                t0 = time.perf_counter()
                with tracer.start_as_current_span("embedding.batch_generate") as span:
                    span.set_attribute("embedding.provider", self._provider_name)
                    span.set_attribute("embedding.batch_size", len(batch))
                    vectors = await self._embedding_generator.batch_generate(texts)
                gen_dur = time.perf_counter() - t0
                try:
                    INGESTION_STAGE_DURATION.labels(stage="embedding").observe(gen_dur)
                    EMBEDDING_CHUNKS.labels(
                        provider=self._provider_name, status="success"
                    ).inc(len(batch))
                except Exception:
                    pass

                # 3. Store vectors in VectorStore
                payloads = []
                for c in batch:
                    payloads.append(
                        {
                            "chunk_id": str(c.id),
                            "document_id": str(document_id),
                            "user_id": doc_user_id,
                            "document_scope": doc_scope,
                            "conversation_id": doc_conversation_id,
                            "chunk_index": c.chunk_index,
                            "language": doc_language,
                            "metadata": c.metadata,
                        }
                    )

                t0 = time.perf_counter()
                with tracer.start_as_current_span("qdrant.upsert_vectors") as span:
                    span.set_attribute("qdrant.operation", "upsert")
                    span.set_attribute("qdrant.vectors_count", len(vectors))
                    await self._vector_store.upsert(
                        vectors=vectors,
                        payloads=payloads,
                        ids=[c.id for c in batch],
                    )
                upsert_dur = time.perf_counter() - t0
                try:
                    QDRANT_OPERATION_DURATION.labels(operation="upsert").observe(
                        upsert_dur
                    )
                except Exception:
                    pass

                # 4. Mark status as COMPLETED in DB
                now = self._time_provider.get_now()
                chunk_ids = [c.id for c in batch]
                existing_embs = await self._embedding_repo.get_by_chunk_ids(chunk_ids)
                emb_map = {emb.chunk_id: emb for emb in existing_embs}

                for chunk in batch:
                    current_emb = emb_map.get(chunk.id)
                    current_status = (
                        current_emb.status
                        if current_emb
                        else EmbeddingStatus.GENERATING
                    )
                    EmbeddingStateMachine.validate_transition(
                        current_status, EmbeddingStatus.COMPLETED
                    )

                    emb = Embedding(
                        id=current_emb.id
                        if current_emb
                        else self._uuid_generator.generate(),
                        chunk_id=chunk.id,
                        status=EmbeddingStatus.COMPLETED,
                        metadata=EmbeddingMetadata(
                            provider=self._provider_name,
                            model=self._model_name,
                            dimension=self._dimension,
                            embedding_version=self._embedding_version,
                        ),
                        created_at=current_emb.created_at if current_emb else now,
                        updated_at=now,
                    )
                    await self._embedding_repo.save(emb)
                await self._uow.commit()

            except Exception as batch_error:
                logger.error(
                    f"Failed to process embedding batch of size {len(batch)}: {batch_error}"
                )
                await self._uow.rollback()

                # Compensatory purge: ensure partial vectors in vector store are cleaned up
                try:
                    await self._vector_store.delete_document(document_id)
                except Exception as del_err:
                    logger.warning(
                        f"Failed to purge partial vectors for document {document_id} during batch failure cleanup: {del_err}"
                    )

                # Record batch chunks as FAILED in database
                try:
                    now = self._time_provider.get_now()
                    chunk_ids = [c.id for c in batch]
                    existing_embs = await self._embedding_repo.get_by_chunk_ids(
                        chunk_ids
                    )
                    emb_map = {emb.chunk_id: emb for emb in existing_embs}

                    for chunk in batch:
                        current_emb = emb_map.get(chunk.id)
                        current_status = (
                            current_emb.status
                            if current_emb
                            else EmbeddingStatus.GENERATING
                        )
                        try:
                            EmbeddingStateMachine.validate_transition(
                                current_status, EmbeddingStatus.FAILED
                            )
                        except Exception as te:
                            logger.warning(
                                f"Skipping state transition validation check due to nested error: {te}"
                            )

                        emb = Embedding(
                            id=current_emb.id
                            if current_emb
                            else self._uuid_generator.generate(),
                            chunk_id=chunk.id,
                            status=EmbeddingStatus.FAILED,
                            metadata=EmbeddingMetadata(
                                provider=self._provider_name,
                                model=self._model_name,
                                dimension=self._dimension,
                                embedding_version=self._embedding_version,
                            ),
                            created_at=current_emb.created_at if current_emb else now,
                            updated_at=now,
                        )
                        await self._embedding_repo.save(emb)
                    await self._uow.commit()
                except Exception as fail_db_err:
                    await self._uow.rollback()
                    logger.critical(
                        f"Critical failure recording FAILED embedding state to DB: {fail_db_err}"
                    )

    async def delete_embeddings(self, document_id: UUID) -> None:
        """
        Deletes all embeddings metadata and vectors associated with the document.
        """
        logger.info(f"Deleting embeddings and vectors for document {document_id}")
        try:
            await self._embedding_repo.delete_by_document(document_id)
            await self._uow.commit()
            # Deletion from vector store is executed after PostgreSQL commit.
            await self._vector_store.delete_document(document_id)
        except Exception as e:
            await self._uow.rollback()
            logger.exception(
                f"Failed to delete embeddings for document {document_id}: {e}"
            )
            raise
