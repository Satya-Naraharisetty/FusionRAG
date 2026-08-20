from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.documents.domain.interfaces import ChunkRepository
from app.documents.domain.models import Chunk
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)


class SQLAlchemyChunkRepository(ChunkRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_bulk(self, chunks: list[Chunk]) -> None:
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
        await self._db.flush()

    async def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all chunks associated with a document.
        """
        await self._db.execute(
            delete(SQLAlchemyChunk).where(SQLAlchemyChunk.document_id == document_id)
        )
        await self._db.flush()

    async def list_by_document(self, document_id: UUID) -> list[Chunk]:
        """
        Fetches all chunks associated with a document, sorted by chunk_index.
        """
        result = await self._db.execute(
            select(SQLAlchemyChunk)
            .where(SQLAlchemyChunk.document_id == document_id)
            .order_by(SQLAlchemyChunk.chunk_index.asc())
        )
        db_chunks = result.scalars().all()
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
        result = await self._db.execute(
            select(SQLAlchemyChunk).where(SQLAlchemyChunk.id == chunk_id)
        )
        db_chunk = result.scalar_one_or_none()
        return db_chunk.text if db_chunk else None

    async def load_metadata(self, chunk_id: UUID) -> dict[str, Any] | None:
        """
        Loads the metadata of a single chunk.
        """
        result = await self._db.execute(
            select(SQLAlchemyChunk).where(SQLAlchemyChunk.id == chunk_id)
        )
        db_chunk = result.scalar_one_or_none()
        return db_chunk.metadata_json if db_chunk else None

    async def batch_lookup(self, chunk_ids: list[UUID]) -> list[Chunk]:
        """
        Batch lookups chunks by their IDs.
        Uses eager loading on document to prevent N+1 queries.
        """
        if not chunk_ids:
            return []

        result = await self._db.execute(
            select(SQLAlchemyChunk)
            .options(joinedload(SQLAlchemyChunk.document))
            .where(SQLAlchemyChunk.id.in_(chunk_ids))
        )
        db_chunks = result.scalars().all()

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
                metadata=dict(c.metadata_json) if c.metadata_json else {},
                created_at=c.created_at,
            )
            if c.document:
                chunk.metadata["document_name"] = c.document.original_filename
                chunk.metadata["document_scope"] = c.document.scope
                chunk.metadata["conversation_id"] = (
                    str(c.document.conversation_id)
                    if c.document.conversation_id
                    else None
                )
            chunks.append(chunk)

        return chunks

    async def verify_document_ownership(
        self, document_ids: list[UUID], user_id: UUID
    ) -> bool:
        """
        Verifies that all specified document_ids belong to the user_id.
        """
        if not document_ids:
            return True

        unique_ids = list(set(document_ids))
        from sqlalchemy import func

        result = await self._db.execute(
            select(func.count(SQLAlchemyDocument.id)).where(
                SQLAlchemyDocument.id.in_(unique_ids),
                SQLAlchemyDocument.user_id == user_id,
            )
        )
        count = result.scalar_one()
        return count == len(unique_ids)

    async def get_filtered_chunks(
        self,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        query = (
            select(SQLAlchemyChunk)
            .options(joinedload(SQLAlchemyChunk.document))
            .join(SQLAlchemyDocument)
            .where(SQLAlchemyDocument.user_id == user_id)
        )
        if document_ids:
            query = query.where(SQLAlchemyChunk.document_id.in_(document_ids))

        result = await self._db.execute(query)
        db_chunks = result.scalars().all()

        chunks = []
        for c in db_chunks:
            meta = dict(c.metadata_json) if c.metadata_json else {}

            # Tags filter
            if tags:
                chunk_tags = meta.get("tags") or []
                if isinstance(chunk_tags, str):
                    chunk_tags = [chunk_tags]
                if not any(t in chunk_tags for t in tags):
                    continue

            # Metadata filter
            if filter_metadata:
                match = True
                for k, v in filter_metadata.items():
                    if meta.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            chunk = Chunk(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                text=c.text,
                character_start=c.character_start,
                character_end=c.character_end,
                token_estimate=c.token_estimate,
                metadata=meta,
                created_at=c.created_at,
            )
            if c.document:
                chunk.metadata["document_name"] = c.document.original_filename
                chunk.metadata["document_scope"] = c.document.scope
                chunk.metadata["conversation_id"] = (
                    str(c.document.conversation_id)
                    if c.document.conversation_id
                    else None
                )
            chunks.append(chunk)

        return chunks

    async def get_chunks_metadata_stats(self, user_id: UUID) -> dict[str, Any]:
        from sqlalchemy import func

        result = await self._db.execute(
            select(
                func.count(SQLAlchemyChunk.id).label("count"),
                func.max(SQLAlchemyChunk.created_at).label("max_created_at"),
            )
            .join(SQLAlchemyDocument)
            .where(SQLAlchemyDocument.user_id == user_id)
        )
        row = result.first()
        return {
            "count": row[0] if row and row[0] is not None else 0,
            "max_created_at": row[1] if row and row[1] is not None else None,
        }

    async def get_allowed_document_ids(self, retrieval_scope: Any) -> list[UUID]:
        """
        Resolves the list of document IDs the user is allowed to access
        based on the DocumentRetrievalScope.

        Returns [] immediately (without a DB query) when both include_* flags
        are False, since no document can match an empty scope.
        """
        include_library = retrieval_scope.include_library_documents
        include_conversation = (
            retrieval_scope.include_conversation_documents
            and retrieval_scope.conversation_id
        )
        if not include_library and not include_conversation:
            return []

        from sqlalchemy import and_, or_

        query = select(SQLAlchemyDocument.id).where(
            SQLAlchemyDocument.user_id == retrieval_scope.user_id
        )

        if retrieval_scope.document_ids is not None:
            query = query.where(SQLAlchemyDocument.id.in_(retrieval_scope.document_ids))

        conditions = []
        if include_library:
            conditions.append(SQLAlchemyDocument.scope == "LIBRARY")

        if include_conversation:
            conditions.append(
                and_(
                    SQLAlchemyDocument.scope == "CONVERSATION",
                    SQLAlchemyDocument.conversation_id
                    == retrieval_scope.conversation_id,
                )
            )

        query = query.where(or_(*conditions))
        try:
            result = await self._db.execute(query)
        except TypeError:
            sync_db: Any = self._db
            result = sync_db.execute(query)
        db_doc_ids = result.all()
        return [row[0] for row in db_doc_ids]
