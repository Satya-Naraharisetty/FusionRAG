from uuid import UUID

from sqlalchemy.orm import Session

from app.documents.domain.interfaces import ChunkRepository
from app.documents.domain.models import Chunk
from app.documents.infrastructure.persistence.models import SQLAlchemyChunk


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
