import logging
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.documents.domain.interfaces import VectorStore

logger = logging.getLogger(__name__)


class QdrantVectorStore(VectorStore):
    """
    Qdrant implementation of the VectorStore.
    Encapsulates AsyncQdrantClient calls and isolates Qdrant details behind the VectorStore domain interface.
    """

    def __init__(
        self, client: AsyncQdrantClient, collection_name: str, dimension: int
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._dimension = dimension
        # Fields whose payload indexes have been successfully ensured on the
        # Qdrant collection.
        self._indexed_fields: set[str] = set()

    # Fields filtered on by search / delete_document. They must be
    # indexed in Qdrant or filtered searches fail with
    # "Index required but not found" errors.
    _FILTERABLE_FIELDS = (
        "user_id",
        "document_id",
        "document_scope",
        "conversation_id",
        "tags",
        "metadata",
    )

    async def _ensure_payload_indexes(self) -> None:
        """
        Idempotently create keyword payload indexes for filterable fields.
        """
        for field in self._FILTERABLE_FIELDS:
            if field in self._indexed_fields:
                continue
            try:
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                # create_payload_index is idempotent for an identical schema;
                # a failure here means filtered searches on this field will
                # 500, so log at warning rather than silently swallowing it.
                logger.warning(f"Payload index for field {field!r} not created: {e}")
            else:
                self._indexed_fields.add(field)

    async def _ensure_collection(self) -> None:
        try:
            await self._client.get_collection(self._collection_name)
        except Exception:
            logger.info(
                f"Creating Qdrant collection {self._collection_name} since it does not exist."
            )
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )
        if not self._indexed_fields.issuperset(self._FILTERABLE_FIELDS):
            await self._ensure_payload_indexes()

    async def upsert(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[UUID],
    ) -> None:
        await self._ensure_collection()
        points = []
        for vid, vector, payload in zip(ids, vectors, payloads, strict=True):
            points.append(
                PointStruct(
                    id=str(vid),
                    vector=vector,
                    payload=payload,
                )
            )
        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
        )

    async def delete(self, ids: list[UUID]) -> None:
        await self._ensure_collection()
        if not ids:
            return
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=PointIdsList(points=[str(vid) for vid in ids]),
        )

    async def delete_document(self, document_id: UUID) -> None:
        await self._ensure_collection()
        await self._client.delete(
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

    async def health(self) -> bool:
        try:
            # 1. Check reachability
            await self._client.get_collections()
            # 2. Ensure collection exists
            await self._ensure_collection()
            # 3. Verify dimension matches
            collection_info = await self._client.get_collection(self._collection_name)
            vectors_config = collection_info.config.params.vectors

            # Qdrant client vectors config can be multiple vectors or single vector config
            if vectors_config is None:
                vector_size = None
            elif isinstance(vectors_config, dict):
                first_config = next(iter(vectors_config.values()), None)
                vector_size = getattr(first_config, "size", None)
            else:
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

    async def search(
        self,
        query_vector: list[float],
        top_k: int,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
        retrieval_scope: Any | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_collection()

        must_conditions: list[Any] = [
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
                    match=MatchAny(any=[str(d_id) for d_id in document_ids]),
                )
            )

        if tags:
            from qdrant_client.models import MatchAny

            must_conditions.append(
                FieldCondition(
                    key="tags",
                    match=MatchAny(any=tags),
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

        if retrieval_scope is not None:
            scope_conditions: list[Any] = []
            if retrieval_scope.include_library_documents:
                scope_conditions.append(
                    FieldCondition(
                        key="document_scope",
                        match=MatchValue(value="LIBRARY"),
                    )
                )
            if (
                retrieval_scope.include_conversation_documents
                and retrieval_scope.conversation_id
            ):
                scope_conditions.append(
                    Filter(
                        must=[
                            FieldCondition(
                                key="document_scope",
                                match=MatchValue(value="CONVERSATION"),
                            ),
                            FieldCondition(
                                key="conversation_id",
                                match=MatchValue(
                                    value=str(retrieval_scope.conversation_id)
                                ),
                            ),
                        ]
                    )
                )
            if scope_conditions:
                must_conditions.append(Filter(should=scope_conditions))

        results = await self._client.search(
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
