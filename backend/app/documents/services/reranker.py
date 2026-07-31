from app.documents.domain.interfaces import Reranker
from app.documents.domain.models import RetrievedChunk

class IdentityReranker(Reranker):
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        return chunks
