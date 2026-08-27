import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import ChunkRepository, SparseIndex
from app.documents.domain.models import Chunk, RetrievedChunk
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyChunk,
    SQLAlchemyDocument,
)

logger = logging.getLogger(__name__)


class PostgresSparseRetriever(SparseIndex):
    """
    Shared Sparse Retrieval Engine using PostgreSQL Full-Text Search (TSVECTOR + GIN).
    Replaces process-local InMemoryBM25Index in production for multi-worker consistency.
    Uses ts_rank_cd for cover-density ranking, preserving ordinal rank compatibility for Weighted RRF.
    """

    def __init__(
        self,
        db: AsyncSession,
        chunk_repo: ChunkRepository | None = None,
        language: str = "english",
    ) -> None:
        self._db = db
        self._chunk_repo = chunk_repo
        self._language = language

    async def index_chunks(self, user_id: UUID, chunks: list[Chunk]) -> None:
        """
        No-op for PostgreSQL FTS.
        search_vector is a generated column on document_chunks, automatically
        and transactionally created when chunks are inserted.
        """
        logger.debug(
            f"PostgresSparseRetriever.index_chunks: {len(chunks)} chunks automatically indexed via PostgreSQL generated tsvector."
        )

    async def search(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_scope: Any | None = None,
    ) -> list[RetrievedChunk]:
        """
        Executes safe Full-Text Search against document_chunks using PostgreSQL websearch_to_tsquery.
        Applies tenant isolation, retrieval scope permissions, and metadata filters.
        """
        start_time = time.time()

        if not query or not query.strip() or top_k <= 0:
            return []

        clean_query = query.strip()

        # 1. Resolve allowed document IDs based on retrieval scope or explicit document_ids
        allowed_doc_ids: list[UUID] | None = None

        if retrieval_scope is not None:
            if self._chunk_repo:
                allowed_doc_ids = await self._chunk_repo.get_allowed_document_ids(
                    retrieval_scope
                )
            else:
                # Direct fallback if chunk_repo is not injected
                allowed_doc_ids = await self._resolve_allowed_document_ids(
                    retrieval_scope
                )

            if not allowed_doc_ids:
                return []

            if document_ids is not None:
                allowed_set = set(allowed_doc_ids)
                allowed_doc_ids = [d for d in document_ids if d in allowed_set]
                if not allowed_doc_ids:
                    return []
        elif document_ids is not None:
            allowed_doc_ids = document_ids

        # 2. Build PostgreSQL Full-Text Search expressions
        tsquery = func.websearch_to_tsquery(self._language, clean_query)
        rank_expr = func.ts_rank_cd(SQLAlchemyChunk.search_vector, tsquery).label(
            "rank_score"
        )

        stmt = (
            select(SQLAlchemyChunk, SQLAlchemyDocument, rank_expr)
            .join(
                SQLAlchemyDocument, SQLAlchemyChunk.document_id == SQLAlchemyDocument.id
            )
            .where(
                SQLAlchemyDocument.user_id == user_id,
                SQLAlchemyChunk.search_vector.op("@@")(tsquery),
            )
        )

        if allowed_doc_ids is not None:
            stmt = stmt.where(SQLAlchemyChunk.document_id.in_(allowed_doc_ids))

        # Preserve deterministic ordering for ranking ties
        stmt = stmt.order_by(
            rank_expr.desc(),
            SQLAlchemyChunk.document_id.asc(),
            SQLAlchemyChunk.chunk_index.asc(),
        )

        # Over-fetch slightly if in-memory metadata filters are active
        fetch_limit = top_k * 3 if (tags or filter_metadata) else top_k
        stmt = stmt.limit(fetch_limit)

        try:
            result = await self._db.execute(stmt)
            rows = result.all()
        except Exception as e:
            logger.error(f"PostgresSparseRetriever query error: {e}")
            return []

        if not rows:
            return []

        # 3. Apply post-query metadata & tag filtering
        candidates: list[tuple[SQLAlchemyChunk, SQLAlchemyDocument, float]] = []
        for row in rows:
            chunk_row: SQLAlchemyChunk = row[0]
            doc_row: SQLAlchemyDocument = row[1]
            rank_score: float = float(row[2]) if row[2] is not None else 0.0

            meta = dict(chunk_row.metadata_json) if chunk_row.metadata_json else {}

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

            candidates.append((chunk_row, doc_row, rank_score))
            if len(candidates) >= top_k:
                break

        if not candidates:
            return []

        # 4. Calculate min-max normalized score (matching InMemoryBM25Index interface contract)
        scores = [c[2] for c in candidates]
        max_score = scores[0]
        min_score = scores[-1]
        score_range = max_score - min_score

        retrieved_chunks: list[RetrievedChunk] = []
        for chunk_row, doc_row, score in candidates:
            if score_range > 0:
                normalized_score = (score - min_score) / score_range
            else:
                normalized_score = 1.0

            meta = dict(chunk_row.metadata_json) if chunk_row.metadata_json else {}
            meta["document_name"] = doc_row.original_filename or doc_row.filename
            meta["document_scope"] = doc_row.scope
            meta["conversation_id"] = (
                str(doc_row.conversation_id) if doc_row.conversation_id else None
            )

            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_row.id,
                    document_id=chunk_row.document_id,
                    document_name=doc_row.original_filename or doc_row.filename,
                    text=chunk_row.text,
                    similarity_score=score,
                    normalized_score=normalized_score,
                    rerank_score=None,
                    metadata=meta,
                    chunk_index=chunk_row.chunk_index,
                )
            )

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"sparse_retrieval.executed: retriever=postgres_fts user_id={user_id} "
            f"matches={len(retrieved_chunks)} top_k={top_k} duration_ms={duration_ms:.2f}"
        )

        return retrieved_chunks

    async def _resolve_allowed_document_ids(self, retrieval_scope: Any) -> list[UUID]:
        """Resolves allowed document IDs when chunk_repo is not directly injected."""
        include_library = getattr(retrieval_scope, "include_library_documents", False)
        conv_id = getattr(retrieval_scope, "conversation_id", None)
        include_conversation = (
            getattr(retrieval_scope, "include_conversation_documents", False)
            and conv_id is not None
        )

        if not include_library and not include_conversation:
            return []

        from sqlalchemy import and_, or_

        stmt = select(SQLAlchemyDocument.id).where(
            SQLAlchemyDocument.user_id == retrieval_scope.user_id
        )

        scope_filter = getattr(retrieval_scope, "document_ids", None)
        if scope_filter is not None:
            stmt = stmt.where(SQLAlchemyDocument.id.in_(scope_filter))

        conditions = []
        if include_library:
            conditions.append(SQLAlchemyDocument.scope == "LIBRARY")
        if include_conversation:
            conditions.append(
                and_(
                    SQLAlchemyDocument.scope == "CONVERSATION",
                    SQLAlchemyDocument.conversation_id == conv_id,
                )
            )

        stmt = stmt.where(or_(*conditions))
        res = await self._db.execute(stmt)
        return [r[0] for r in res.all()]
