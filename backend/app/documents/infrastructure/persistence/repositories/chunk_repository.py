from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.documents.domain.interfaces import ChunkRepository
from app.documents.domain.models import Chunk
from app.documents.infrastructure.persistence.models import SQLAlchemyChunk, SQLAlchemyDocument


class SQLAlchemyChunkRepository(ChunkRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save_bulk(self, chunks: list[Chunk]) -> None:
        """
        Bulk inserts chunks.
        """
        db_chunks = [
            SQLAlchemyChunk(
                id=chunk.id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                character_start=chunk.character_start,
                character_end=chunk.character_end,
                token_estimate=chunk.token_estimate,
                metadata_json=chunk.metadata,
                created_at=chunk.created_at,
            )
            for chunk in chunks
        ]
        self._db.add_all(db_chunks)
        self._db.flush()

    def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all chunks associated with a document.
        """
        self._db.query(SQLAlchemyChunk).filter(
            SQLAlchemyChunk.document_id == document_id
        ).delete(synchronize_session=False)
        self._db.flush()

    def list_by_document(self, document_id: UUID) -> list[Chunk]:
        """
        Fetches all chunks associated with a document, sorted by chunk_index.
        """
        db_chunks = (
            self._db.query(SQLAlchemyChunk)
            .filter(SQLAlchemyChunk.document_id == document_id)
            .order_by(SQLAlchemyChunk.chunk_index.asc())
            .all()
        )
        return [
            Chunk(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                text=c.text,
                character_start=c.character_start,
                character_end=c.character_end,
                token_estimate=c.token_estimate,
                metadata=c.metadata_json,
                created_at=c.created_at,
            )
            for c in db_chunks
        ]

    async def load_chunk_text(self, chunk_id: UUID) -> str | None:
        """
        Loads the text of a single chunk.
        """
        db_chunk = (
            self._db.query(SQLAlchemyChunk)
            .filter(SQLAlchemyChunk.id == chunk_id)
            .first()
        )
        return db_chunk.text if db_chunk else None

    async def load_metadata(self, chunk_id: UUID) -> dict[str, Any] | None:
        """
        Loads the metadata of a single chunk.
        """
        db_chunk = (
            self._db.query(SQLAlchemyChunk)
            .filter(SQLAlchemyChunk.id == chunk_id)
            .first()
        )
        return db_chunk.metadata_json if db_chunk else None

    async def batch_lookup(self, chunk_ids: list[UUID]) -> list[Chunk]:
        """
        Batch lookups chunks by their IDs.
        Uses eager loading on document to prevent N+1 queries.
        """
        if not chunk_ids:
            return []

        db_chunks = (
            self._db.query(SQLAlchemyChunk)
            .options(joinedload(SQLAlchemyChunk.document))
            .filter(SQLAlchemyChunk.id.in_(chunk_ids))
            .all()
        )

        chunks = []
        for c in db_chunks:
            chunk = Chunk(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                text=c.text,
                character_start=c.character_start,
                character_end=c.character_end,
                token_estimate=c.token_estimate,
                metadata=dict(c.metadata_json),
                created_at=c.created_at,
            )
            # Embed original filename in metadata so it is accessible downstream
            chunk.metadata["document_name"] = c.document.original_filename
            chunks.append(chunk)

        return chunks

    async def verify_document_ownership(self, document_ids: list[UUID], user_id: UUID) -> bool:
        """
        Verifies that all specified document_ids belong to the user_id.
        """
        if not document_ids:
            return True

        unique_ids = list(set(document_ids))
        count = (
            self._db.query(SQLAlchemyDocument)
            .filter(
                SQLAlchemyDocument.id.in_(unique_ids),
                SQLAlchemyDocument.user_id == user_id,
            )
            .count()
        )
        return count == len(unique_ids)
