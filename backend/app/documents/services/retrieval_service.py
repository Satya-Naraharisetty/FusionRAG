import asyncio
import time
from typing import Any
from uuid import UUID

from app.documents.domain.exceptions import UnauthorizedDocumentAccess
from app.documents.domain.interfaces import (
    ChunkRepository,
    EmbeddingGenerator,
    SearchRanker,
    VectorStore,
)
from app.documents.domain.models import RetrievedChunk, SearchResult


class RetrievalService:
    """
    RetrievalService coordinates the semantic search pipeline.
    It takes a text query, retrieves matching document chunks from the vector store,
    performs batch metadata loading, scales similarity scores, filters by a threshold,
    ranks the result, and returns a structured SearchResult.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        chunk_repo: ChunkRepository,
        ranker: SearchRanker,
        similarity_threshold: float = 0.25,
        search_timeout: float = 3.0,
    ) -> None:
        self._embedding_generator = embedding_generator
        self._vector_store = vector_store
        self._chunk_repo = chunk_repo
        self._ranker = ranker
        self._similarity_threshold = similarity_threshold
        self._search_timeout = search_timeout

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> SearchResult:
        start_time = time.perf_counter()

        # 1. Ownership Verification (Never trust incoming document IDs)
        if document_ids:
            # Deduplicate incoming document IDs to ensure correct behavior and avoid redundant checks
            unique_doc_ids = list(set(document_ids))
            ownership_ok = await self._chunk_repo.verify_document_ownership(
                unique_doc_ids, user_id
            )
            if not ownership_ok:
                raise UnauthorizedDocumentAccess(
                    "Unauthorized document access: one or more specified document IDs do not belong to you."
                )
        else:
            unique_doc_ids = None

        # 2. Generate Query Embedding
        # Run third-party API embedding generator in thread pool to prevent blocking the event loop
        query_vector = await asyncio.to_thread(
            self._embedding_generator.generate, query
        )

        # 3. Vector Search (applying user context, document IDs, tags, metadata, and timeout)
        search_results = await self._vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            user_id=user_id,
            document_ids=unique_doc_ids,
            tags=tags,
            filter_metadata=filter_metadata,
            timeout=self._search_timeout,
        )

        if not search_results:
            end_time = time.perf_counter()
            return SearchResult(
                original_query=query,
                retrieval_time=end_time - start_time,
                total_matches=0,
                retrieved_chunks=[],
            )

        # 4. Batch Lookup chunks to resolve text and metadata in a single query (avoid N+1)
        chunk_ids = [res["id"] for res in search_results]
        db_chunks = await self._chunk_repo.batch_lookup(chunk_ids)
        chunk_map = {c.id: c for c in db_chunks}

        # 5. Populate RetrievedChunks, normalize scores, and apply threshold filtering
        retrieved_chunks = []
        for res in search_results:
            cid = res["id"]
            raw_score = res["score"]
            chunk = chunk_map.get(cid)
            if not chunk:
                continue

            # Scale cosine similarity score from [-1.0, 1.0] to [0.0, 1.0]
            # Clamp to guarantee value bounds
            normalized_score = max(0.0, min(1.0, (raw_score + 1.0) / 2.0))

            # Apply similarity threshold filtering
            if self._similarity_threshold is not None:
                if raw_score < self._similarity_threshold:
                    continue

            retrieved_chunk = RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.metadata.get("document_name", "Unknown Document"),
                text=chunk.text,
                similarity_score=raw_score,
                normalized_score=normalized_score,
                metadata=chunk.metadata,
                chunk_index=chunk.chunk_index,
            )
            retrieved_chunks.append(retrieved_chunk)

        # 6. Rank Results using the SearchRanker
        ranked_chunks = self._ranker.rank(query, retrieved_chunks)

        end_time = time.perf_counter()
        return SearchResult(
            original_query=query,
            retrieval_time=end_time - start_time,
            total_matches=len(ranked_chunks),
            retrieved_chunks=ranked_chunks,
        )
