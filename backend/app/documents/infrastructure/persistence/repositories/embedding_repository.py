from uuid import UUID

from sqlalchemy.orm import Session

from app.documents.domain.interfaces import EmbeddingRepository
from app.documents.domain.models import Embedding, EmbeddingMetadata, EmbeddingStatus
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyEmbedding,
)


class SQLAlchemyEmbeddingRepository(EmbeddingRepository):
    """
    SQLAlchemy implementation of the EmbeddingRepository.
    Manages embedding metadata records in the relational database.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, embedding: Embedding) -> Embedding:
        db_emb = (
            self._db.query(SQLAlchemyEmbedding)
            .filter(SQLAlchemyEmbedding.chunk_id == embedding.chunk_id)
            .first()
        )
        if not db_emb:
            db_emb = SQLAlchemyEmbedding(
                id=embedding.id,
                chunk_id=embedding.chunk_id,
                embedding_provider=embedding.metadata.provider,
                embedding_model=embedding.metadata.model,
                embedding_dimension=embedding.metadata.dimension,
                embedding_version=embedding.metadata.embedding_version,
                status=embedding.status.value,
                created_at=embedding.created_at,
                updated_at=embedding.updated_at,
            )
            self._db.add(db_emb)
        else:
            db_emb.status = embedding.status.value
            db_emb.embedding_provider = embedding.metadata.provider
            db_emb.embedding_model = embedding.metadata.model
            db_emb.embedding_dimension = embedding.metadata.dimension
            db_emb.embedding_version = embedding.metadata.embedding_version
            db_emb.updated_at = embedding.updated_at

        self._db.flush()
        return self._to_domain(db_emb)

    def get_by_chunk(self, chunk_id: UUID) -> Embedding | None:
        db_emb = (
            self._db.query(SQLAlchemyEmbedding)
            .filter(SQLAlchemyEmbedding.chunk_id == chunk_id)
            .first()
        )
        if not db_emb:
            return None
        return self._to_domain(db_emb)

    def get_by_chunk_ids(self, chunk_ids: list[UUID]) -> list[Embedding]:
        if not chunk_ids:
            return []
        db_embs = (
            self._db.query(SQLAlchemyEmbedding)
            .filter(SQLAlchemyEmbedding.chunk_id.in_(chunk_ids))
            .all()
        )
        return [self._to_domain(emb) for emb in db_embs]

    def delete_by_document(self, document_id: UUID) -> None:
        self._db.query(SQLAlchemyEmbedding).filter(
            SQLAlchemyEmbedding.chunk_id.in_(
                self._db.query(SQLAlchemyChunk.id).filter(
                    SQLAlchemyChunk.document_id == document_id
                )
            )
        ).delete(synchronize_session=False)
        self._db.flush()

    def list_by_document(self, document_id: UUID) -> list[Embedding]:
        db_embs = (
            self._db.query(SQLAlchemyEmbedding)
            .join(SQLAlchemyChunk, SQLAlchemyEmbedding.chunk_id == SQLAlchemyChunk.id)
            .filter(SQLAlchemyChunk.document_id == document_id)
            .all()
        )
        return [self._to_domain(emb) for emb in db_embs]

    def _to_domain(self, db_emb: SQLAlchemyEmbedding) -> Embedding:
        return Embedding(
            id=db_emb.id,
            chunk_id=db_emb.chunk_id,
            status=EmbeddingStatus(db_emb.status),
            metadata=EmbeddingMetadata(
                provider=db_emb.embedding_provider,
                model=db_emb.embedding_model,
                dimension=db_emb.embedding_dimension,
                embedding_version=db_emb.embedding_version,
            ),
            created_at=db_emb.created_at,
            updated_at=db_emb.updated_at,
        )
