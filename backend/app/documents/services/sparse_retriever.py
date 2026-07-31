from uuid import UUID
from typing import Any
from app.documents.domain.interfaces import SparseRetriever, SparseIndex
from app.documents.domain.models import RetrievedChunk

class BM25Retriever(SparseRetriever):
    def __init__(self, sparse_index: SparseIndex) -> None:
        self._sparse_index = sparse_index

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        return await self._sparse_index.search(
            query=query,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
            tags=tags,
            filter_metadata=filter_metadata,
        )
