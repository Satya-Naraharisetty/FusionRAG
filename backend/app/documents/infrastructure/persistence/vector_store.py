import asyncio
import logging
from typing import Any
from uuid import UUID

from app.documents.domain.interfaces import VectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)


class QdrantVectorStore(VectorStore):
    """
    Qdrant implementation of the VectorStore.
    Encapsulates QdrantClient calls and isolates Qdrant details behind the VectorStore domain interface.
    """

    def __init__(
        self, client: QdrantClient, collection_name: str, dimension: int
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._dimension = dimension

    def _ensure_collection(self) -> None:
        try:
            self._client.get_collection(self._collection_name)
        except Exception:
            logger.info(
                f"Creating Qdrant collection {self._collection_name} since it does not exist."
            )
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )

    def upsert(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[UUID],
    ) -> None:
        self._ensure_collection()
        points = []
        for vid, vector, payload in zip(ids, vectors, payloads, strict=True):
            points.append(
                PointStruct(
                    id=str(vid),
                    vector=vector,
                    payload=payload,
                )
            )
        self._client.upsert(
            collection_name=self._collection_name,
            points=points,
        )

    def delete(self, ids: list[UUID]) -> None:
        self._ensure_collection()
        if not ids:
            return
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=PointIdsList(points=[str(vid) for vid in ids]),
        )

    def delete_document(self, document_id: UUID) -> None:
        self._ensure_collection()
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    )
                ]
            ),
        )

    def health(self) -> bool:
        try:
            # 1. Check reachability
            self._client.get_collections()
            # 2. Ensure collection exists
            self._ensure_collection()
            # 3. Verify dimension matches
            collection_info = self._client.get_collection(self._collection_name)
            vectors_config = collection_info.config.params.vectors

            # Qdrant client vectors config can be multiple vectors or single vector config
            if hasattr(vectors_config, "size"):
                vector_size = vectors_config.size
            else:
                # Fallback if config matches different Qdrant schema structure
                vector_size = getattr(vectors_config, "size", None)

            if vector_size != self._dimension:
                logger.error(
                    f"Qdrant collection {self._collection_name} vector dimension mismatch. "
                    f"Configured: {self._dimension}, actual: {vector_size}"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Qdrant health check failed: {e}")
            return False

    def _search_sync(
        self,
        query_vector: list[float],
        top_k: int,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_collection()

        must_conditions = [
            FieldCondition(
                key="user_id",
                match=MatchValue(value=str(user_id)),
            )
        ]

        if document_ids:
            from qdrant_client.models import MatchAny

            must_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any_of=[str(d_id) for d_id in document_ids]),
                )
            )

        if tags:
            from qdrant_client.models import MatchAny

            must_conditions.append(
                FieldCondition(
                    key="tags",
                    match=MatchAny(any_of=tags),
                )
            )

        if filter_metadata:
            for k, v in filter_metadata.items():
                must_conditions.append(
                    FieldCondition(
                        key=f"metadata.{k}",
                        match=MatchValue(value=v),
                    )
                )

        results = self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            query_filter=Filter(must=must_conditions),
            limit=top_k,
            timeout=int(timeout) if timeout is not None else None,
        )

        return [
            {
                "id": UUID(r.id) if isinstance(r.id, str) else r.id,
                "score": r.score,
                "payload": r.payload or {},
            }
            for r in results
        ]

    async def search(
        self,
        query_vector: list[float],
        top_k: int,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Asynchronously searches the vector store using the query vector.
        """
        return await asyncio.to_thread(
            self._search_sync,
            query_vector=query_vector,
            top_k=top_k,
            user_id=user_id,
            document_ids=document_ids,
            tags=tags,
            filter_metadata=filter_metadata,
            timeout=timeout,
        )
