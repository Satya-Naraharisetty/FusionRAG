import logging
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

    def generate_embeddings(self, document_id: UUID, force: bool = False) -> None:
        """
        Generates embeddings for chunks belonging to a document.
        If force=True, deletes existing embeddings and vectors, and regenerates.
        Otherwise, only embeds chunks with FAILED, PENDING, or missing statuses.
        """
        logger.info(
            f"Initiating embedding generation for document {document_id} (force={force})"
        )

        document = self._document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFound(f"Document with ID {document_id} not found.")

        chunks = self._chunk_repo.list_by_document(document_id)
        if not chunks:
            logger.info(f"No chunks found for document {document_id}. Skipping.")
            return

        if force:
            logger.info(
                f"Regeneration requested: clearing existing database metadata and vectors for document {document_id}"
            )
            try:
                self._embedding_repo.delete_by_document(document_id)
                self._uow.commit()
                # Deleting from the vector store is done after DB commit is verified
                self._vector_store.delete_document(document_id)
            except Exception as e:
                self._uow.rollback()
                logger.exception(
                    f"Failed to clear old embeddings/vectors for document {document_id}: {e}"
                )
                raise

        # Retrieve current embedding records
        existing_embeddings = self._embedding_repo.list_by_document(document_id)
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
                    self._embedding_repo.save(emb)
                self._uow.commit()

                # 2. Call embedding generator
                texts = [c.text for c in batch]
                vectors = self._embedding_generator.batch_generate(texts)

                # 3. Store vectors in VectorStore
                payloads = []
                for c in batch:
                    payloads.append(
                        {
                            "chunk_id": str(c.id),
                            "document_id": str(document_id),
                            "user_id": str(document.user_id),
                            "chunk_index": c.chunk_index,
                            "language": document.language or "en",
                            "metadata": c.metadata,
                        }
                    )

                self._vector_store.upsert(
                    vectors=vectors,
                    payloads=payloads,
                    ids=[c.id for c in batch],
                )

                # 4. Mark status as COMPLETED in DB
                now = self._time_provider.get_now()
                for chunk in batch:
                    current_emb = self._embedding_repo.get_by_chunk(chunk.id)
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
                    self._embedding_repo.save(emb)
                self._uow.commit()

            except Exception as batch_error:
                logger.error(
                    f"Failed to process embedding batch of size {len(batch)}: {batch_error}"
                )
                self._uow.rollback()

                # Record batch chunks as FAILED in database
                try:
                    now = self._time_provider.get_now()
                    for chunk in batch:
                        current_emb = self._embedding_repo.get_by_chunk(chunk.id)
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
                        self._embedding_repo.save(emb)
                    self._uow.commit()
                except Exception as fail_db_err:
                    self._uow.rollback()
                    logger.critical(
                        f"Critical failure recording FAILED embedding state to DB: {fail_db_err}"
                    )

    def delete_embeddings(self, document_id: UUID) -> None:
        """
        Deletes all embeddings metadata and vectors associated with the document.
        """
        logger.info(f"Deleting embeddings and vectors for document {document_id}")
        try:
            self._embedding_repo.delete_by_document(document_id)
            self._uow.commit()
            # Deletion from vector store is executed after PostgreSQL commit.
            self._vector_store.delete_document(document_id)
        except Exception as e:
            self._uow.rollback()
            logger.exception(
                f"Failed to delete embeddings for document {document_id}: {e}"
            )
            raise
