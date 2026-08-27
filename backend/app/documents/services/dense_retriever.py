import inspect
from typing import Any
from uuid import UUID

from app.documents.domain.interfaces import (
    ChunkRepository,
    DenseRetriever,
    EmbeddingGenerator,
    VectorStore,
)
from app.documents.domain.models import RetrievedChunk


class QdrantDenseRetriever(DenseRetriever):
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        chunk_repo: ChunkRepository,
        similarity_threshold: float = 0.25,
        search_timeout: float = 3.0,
    ) -> None:
        self._embedding_generator = embedding_generator
        self._vector_store = vector_store
        self._chunk_repo = chunk_repo
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
        retrieval_scope: Any | None = None,
    ) -> list[RetrievedChunk]:
        # 1. Generate Query Embedding
        gen_res = self._embedding_generator.generate(query)
        if inspect.isawaitable(gen_res):
            query_vector = await gen_res
        else:
            query_vector = gen_res

        # 2. Vector Search (applying user context, document IDs, tags, metadata, and timeout)
        import time

        from app.core.telemetry import QDRANT_OPERATION_DURATION

        t0 = time.perf_counter()
        search_results = await self._vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            user_id=user_id,
            document_ids=document_ids,
            tags=tags,
            filter_metadata=filter_metadata,
            timeout=self._search_timeout,
            retrieval_scope=retrieval_scope,
        )
        search_dur = time.perf_counter() - t0
        try:
            QDRANT_OPERATION_DURATION.labels(operation="search").observe(search_dur)
        except Exception:
            pass

        if not search_results:
            return []

        # 3. Batch Lookup chunks to resolve text and metadata in a single query
        chunk_ids = [res["id"] for res in search_results]
        db_chunks = await self._chunk_repo.batch_lookup(chunk_ids)
        chunk_map = {c.id: c for c in db_chunks}

        # 4. Populate RetrievedChunks, normalize scores, and apply threshold filtering
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

        return retrieved_chunks
