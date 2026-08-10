import asyncio
import logging
import math
import re
from collections import Counter
from typing import Any
from uuid import UUID

from app.documents.domain.interfaces import ChunkRepository, IndexCache, SparseIndex
from app.documents.domain.models import Chunk, RetrievedChunk

logger = logging.getLogger(__name__)


def tokenize(text: str) -> list[str]:
    # Lowercase, punctuation cleanup, and whitespace split
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        """
        Initializes the BM25 scorer.

        Args:
            corpus: A list of tokenized documents.
            k1: Term frequency scaling parameter (default: 1.5).
                Controls term frequency saturation. A higher value increases the importance
                of multiple occurrences of a term, while a lower value makes term weight
                saturate faster. 1.5 is the standard Lucene/Elasticsearch default for English.
            b: Document length normalization parameter (default: 0.75).
                Controls scaling by document length. b=1.0 scales term weights fully by
                document length, and b=0.0 turns off length normalization entirely.
                0.75 is the industry-standard default.
        """
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = (
            sum(len(doc) for doc in corpus) / self.corpus_size
            if self.corpus_size > 0
            else 0
        )
        self.doc_freqs: Counter[str] = Counter()
        self.doc_lengths: list[int] = []
        self.doc_term_counts = []

        for doc in corpus:
            self.doc_lengths.append(len(doc))
            counts = Counter(doc)
            self.doc_term_counts.append(counts)
            for term in counts.keys():
                self.doc_freqs[term] += 1

        self.idf = {}
        for term, freq in self.doc_freqs.items():
            # Standard BM25 IDF with a floor of 0
            val = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)
            self.idf[term] = max(0.0001, val)  # ensure positive IDF

    def get_scores(self, query: list[str]) -> list[float]:
        scores = []
        for i in range(self.corpus_size):
            score = 0.0
            doc_len = self.doc_lengths[i]
            term_counts = self.doc_term_counts[i]
            for term in query:
                if term in term_counts:
                    tf = term_counts[term]
                    idf = self.idf.get(term, 0.0)
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (
                        1.0 - self.b + self.b * (doc_len / self.avgdl)
                    )
                    score += idf * (numerator / denominator)
            scores.append(score)
        return scores


class InMemoryBM25Index(SparseIndex):
    def __init__(
        self,
        chunk_repo: ChunkRepository,
        index_cache: IndexCache,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """
        Initializes the InMemory BM25 Index.

        Args:
            chunk_repo: The repository to fetch chunk documents from.
            index_cache: The cache layer to prevent redundant index rebuilds.
            k1: Term frequency scaling parameter (default: 1.5).
            b: Document length normalization parameter (default: 0.75).
        """
        self._chunk_repo = chunk_repo
        self._index_cache = index_cache
        self._k1 = k1
        self._b = b
        self._lock = asyncio.Lock()

    async def _ensure_indexed(self, user_id: UUID) -> None:
        # Get DB stats to check drift
        db_stats = await self._chunk_repo.get_chunks_metadata_stats(user_id)

        # Acquire lock to build/rebuild index
        async with self._lock:
            cache_stats = self._index_cache.get_stats(user_id)
            if cache_stats:
                if cache_stats.get("count") == db_stats.get(
                    "count"
                ) and cache_stats.get("max_created_at") == db_stats.get(
                    "max_created_at"
                ):
                    # Cache is fresh
                    return

            # Stale or missing cache - rebuild
            logger.info(
                f"Rebuilding BM25 index for user {user_id} due to cache miss/stats mismatch."
            )
            chunks = await self._chunk_repo.get_filtered_chunks(user_id=user_id)

            if not chunks:
                self._index_cache.set(
                    user_id=user_id,
                    index_data={"chunks": [], "bm25": None},
                    stats=db_stats,
                )
                return

            corpus = [tokenize(c.text) for c in chunks]
            bm25 = BM25(corpus, k1=self._k1, b=self._b)

            self._index_cache.set(
                user_id=user_id,
                index_data={"chunks": chunks, "bm25": bm25},
                stats=db_stats,
            )

    async def index_chunks(self, user_id: UUID, chunks: list[Chunk]) -> None:
        # Directly invalidate cache, triggering ensure_indexed to rebuild on next search.
        async with self._lock:
            self._index_cache.invalidate(user_id)

    async def search(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        # 1. Ensure cache is populated and synchronized
        await self._ensure_indexed(user_id)

        # 2. Retrieve from cache
        async with self._lock:
            index_data = self._index_cache.get(user_id)
            if (
                not index_data
                or not index_data.get("chunks")
                or not index_data.get("bm25")
            ):
                return []

            chunks = index_data["chunks"]
            bm25 = index_data["bm25"]

        # 3. Filter candidates based on document_ids, tags, and metadata
        candidates = []
        candidate_indices = []

        for idx, chunk in enumerate(chunks):
            # Document ID filter
            if document_ids is not None and chunk.document_id not in document_ids:
                continue

            # Tags filter
            if tags:
                chunk_tags = chunk.metadata.get("tags") or []
                if isinstance(chunk_tags, str):
                    chunk_tags = [chunk_tags]
                if not any(t in chunk_tags for t in tags):
                    continue

            # Metadata filter
            if filter_metadata:
                match = True
                for k, v in filter_metadata.items():
                    if chunk.metadata.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            candidates.append(chunk)
            candidate_indices.append(idx)

        if not candidates:
            return []

        # 4. Score query using the pre-computed BM25 index
        query_tokens = tokenize(query)
        all_scores = bm25.get_scores(query_tokens)

        scored_candidates = []
        for chunk, orig_idx in zip(candidates, candidate_indices, strict=True):
            score = all_scores[orig_idx]
            if score > 0.0:  # Only matching chunks
                scored_candidates.append((chunk, score))

        if not scored_candidates:
            return []

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        scored_candidates = scored_candidates[:top_k]

        # Calculate min-max normalized score
        scores_list = [sc[1] for sc in scored_candidates]
        max_score = scores_list[0]
        min_score = scores_list[-1]
        score_range = max_score - min_score

        retrieved_chunks = []
        for chunk, score in scored_candidates:
            if score_range > 0:
                normalized_score = (score - min_score) / score_range
            else:
                normalized_score = 1.0

            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_name=chunk.metadata.get(
                        "document_name", "Unknown Document"
                    ),
                    text=chunk.text,
                    similarity_score=score,
                    normalized_score=normalized_score,
                    metadata=chunk.metadata,
                    chunk_index=chunk.chunk_index,
                )
            )

        return retrieved_chunks
