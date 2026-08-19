from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, embedding: Embedding) -> Embedding:
        result = await self._db.execute(
            select(SQLAlchemyEmbedding).where(
                SQLAlchemyEmbedding.chunk_id == embedding.chunk_id
            )
        )
        db_emb = result.scalar_one_or_none()
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

        await self._db.flush()
        await self._db.refresh(db_emb)
        return self._to_domain(db_emb)

    async def get_by_chunk(self, chunk_id: UUID) -> Embedding | None:
        result = await self._db.execute(
            select(SQLAlchemyEmbedding).where(SQLAlchemyEmbedding.chunk_id == chunk_id)
        )
        db_emb = result.scalar_one_or_none()
        if not db_emb:
            return None
        return self._to_domain(db_emb)

    async def get_by_chunk_ids(self, chunk_ids: list[UUID]) -> list[Embedding]:
        if not chunk_ids:
            return []
        result = await self._db.execute(
            select(SQLAlchemyEmbedding).where(
                SQLAlchemyEmbedding.chunk_id.in_(chunk_ids)
            )
        )
        db_embs = result.scalars().all()
        return [self._to_domain(emb) for emb in db_embs]

    async def delete_by_document(self, document_id: UUID) -> None:
        chunk_ids_stmt = select(SQLAlchemyChunk.id).where(
            SQLAlchemyChunk.document_id == document_id
        )
        await self._db.execute(
            delete(SQLAlchemyEmbedding).where(
                SQLAlchemyEmbedding.chunk_id.in_(chunk_ids_stmt)
            )
        )
        await self._db.flush()

    async def list_by_document(self, document_id: UUID) -> list[Embedding]:
        result = await self._db.execute(
            select(SQLAlchemyEmbedding)
            .join(SQLAlchemyChunk, SQLAlchemyEmbedding.chunk_id == SQLAlchemyChunk.id)
            .where(SQLAlchemyChunk.document_id == document_id)
        )
        db_embs = result.scalars().all()
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
