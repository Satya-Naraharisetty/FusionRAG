import logging
from typing import Any
from uuid import UUID

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

from app.documents.domain.interfaces import VectorStore

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
