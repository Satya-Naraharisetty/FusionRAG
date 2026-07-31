from app.documents.domain.interfaces import SearchRanker
from app.documents.domain.models import RetrievedChunk


class SemanticSearchRanker(SearchRanker):
    """
    Initial ranker implementation.
    Orders chunks by their raw cosine similarity score in descending order.
    """

    def rank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        return sorted(chunks, key=lambda c: c.similarity_score, reverse=True)
