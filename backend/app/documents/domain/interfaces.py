import builtins
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.documents.domain.models import (
    Chunk,
    CleanupJob,
    Document,
    DocumentRetrievalScope,
    Embedding,
    ExtractionResult,
    ProcessedQuery,
    RetrievedChunk,
)


class StorageProvider(ABC):
    @abstractmethod
    async def save(
        self, filename: str, content: bytes, user_id: UUID, document_id: UUID
    ) -> str:
        """
        Saves file content to storage and returns a unique key/relative path.
        """
        pass

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """
        Retrieves file content by unique key.
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Deletes file content from storage.
        """
        pass

    @abstractmethod
    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generates a direct upload URL.
        """
        pass

    @abstractmethod
    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generates a direct download URL.
        """
        pass


class DocumentExtractor(ABC):
    @abstractmethod
    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses document bytes and returns the raw text and metadata.
        """
        pass


class ChecksumGenerator(ABC):
    @abstractmethod
    def generate(self, content: bytes) -> str:
        """
        Generates a secure hash (e.g. SHA-256) of the content.
        """
        pass


class TaskQueue(ABC):
    @abstractmethod
    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """
        Enqueues a task for background processing.
        """
        pass


class DocumentRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Document | None:
        """
        Fetches a document by its ID.
        """
        pass

    @abstractmethod
    async def get_by_id_for_update(self, id: UUID) -> Document | None:
        """
        Fetches a document by its ID and locks the row (SELECT FOR UPDATE).
        """
        pass

    @abstractmethod
    async def get_by_checksum_and_user(
        self, checksum: str, user_id: UUID
    ) -> Document | None:
        """
        Checks if a document with this checksum already exists for the given user.
        """
        pass

    @abstractmethod
    async def list_by_user(self, user_id: UUID) -> list[Document]:
        """
        Lists all documents belonging to a user.
        """
        pass

    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> list[Document]:
        """
        Lists all documents belonging to a conversation.
        """
        pass

    @abstractmethod
    async def save(self, document: Document) -> Document:
        """
        Persists or updates a document.
        """
        pass

    @abstractmethod
    async def delete(self, id: UUID) -> None:
        """
        Deletes a document from the database.
        """
        pass


class ChunkRepository(ABC):
    @abstractmethod
    async def save_bulk(self, chunks: list[Chunk]) -> None:
        """
        Saves a list of document chunks in a bulk transaction.
        """
        pass

    @abstractmethod
    async def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all chunks associated with a document.
        """
        pass

    @abstractmethod
    async def list_by_document(self, document_id: UUID) -> list[Chunk]:
        """
        Retrieves all chunks associated with a document, sorted by chunk_index.
        """
        pass

    @abstractmethod
    async def load_chunk_text(self, chunk_id: UUID) -> str | None:
        """
        Loads the text of a single chunk.
        """
        pass

    @abstractmethod
    async def load_metadata(self, chunk_id: UUID) -> dict[str, Any] | None:
        """
        Loads the metadata of a single chunk.
        """
        pass

    @abstractmethod
    async def batch_lookup(self, chunk_ids: list[UUID]) -> list[Chunk]:
        """
        Batch lookups chunks by their IDs.
        """
        pass

    @abstractmethod
    async def verify_document_ownership(
        self, document_ids: list[UUID], user_id: UUID
    ) -> bool:
        """
        Verifies that all specified document_ids belong to the user_id.
        """
        pass

    @abstractmethod
    async def get_filtered_chunks(
        self,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """
        Retrieves all chunks belonging to a user, with optional filters.
        """
        pass

    @abstractmethod
    async def get_chunks_metadata_stats(self, user_id: UUID) -> dict[str, Any]:
        """
        Returns count and max created_at for a user's chunks to detect drift.
        """
        pass

    @abstractmethod
    async def get_allowed_document_ids(self, retrieval_scope: Any) -> list[UUID]:
        """
        Resolves the list of document IDs the user is allowed to access
        based on the DocumentRetrievalScope.
        """
        pass


class EmbeddingGenerator(ABC):
    @abstractmethod
    async def generate(self, text: str) -> list[float]:
        """
        Generates a vector embedding for a single text.
        """
        pass

    @abstractmethod
    async def batch_generate(self, texts: list[str]) -> list[list[float]]:
        """
        Generates vector embeddings for a list of texts in batch.
        """
        pass


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[UUID],
    ) -> None:
        """
        Upserts vectors with corresponding payloads and IDs.
        """
        pass

    @abstractmethod
    async def delete(self, ids: list[UUID]) -> None:
        """
        Deletes vectors by their vector IDs.
        """
        pass

    @abstractmethod
    async def delete_document(self, document_id: UUID) -> None:
        """
        Deletes all vectors belonging to a document ID.
        """
        pass

    @abstractmethod
    async def health(self) -> bool:
        """
        Checks the health of the vector store connection.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        top_k: int,
        user_id: UUID,
        document_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> list[dict[str, Any]]:
        """
        Asynchronously searches the vector store using the query vector.
        """
        pass


class EmbeddingRepository(ABC):
    @abstractmethod
    async def save(self, embedding: Embedding) -> Embedding:
        """
        Persists or updates an embedding metadata record.
        """
        pass

    @abstractmethod
    async def get_by_chunk(self, chunk_id: UUID) -> Embedding | None:
        """
        Retrieves embedding metadata for a specific chunk.
        """
        pass

    @abstractmethod
    async def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all embedding metadata associated with a document's chunks.
        """
        pass

    @abstractmethod
    async def list_by_document(self, document_id: UUID) -> list[Embedding]:
        """
        Lists all embedding metadata associated with a document's chunks.
        """
        pass

    @abstractmethod
    async def get_by_chunk_ids(self, chunk_ids: list[UUID]) -> list[Embedding]:
        """
        Retrieves embedding metadata for multiple chunks in a single batch query.
        """
        pass


class SearchRanker(ABC):
    @abstractmethod
    def rank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        Ranks a list of retrieved chunks based on the query.
        """
        pass


class QueryProcessor(ABC):
    @abstractmethod
    def process(self, query: str) -> ProcessedQuery:
        """
        Processes a query, returning the processed query string and statistics.
        """
        pass


class IndexCache(ABC):
    @abstractmethod
    def get(self, user_id: UUID) -> Any | None:
        """
        Retrieves cached index data for a user.
        """
        pass

    @abstractmethod
    def set(self, user_id: UUID, index_data: Any, stats: dict[str, Any]) -> None:
        """
        Caches index data for a user, associated with database metadata stats.
        """
        pass

    @abstractmethod
    def get_stats(self, user_id: UUID) -> dict[str, Any] | None:
        """
        Gets the metadata stats associated with the user's cached index.
        """
        pass

    @abstractmethod
    def get_fresh_stats(
        self, user_id: UUID, max_age_seconds: float
    ) -> dict[str, Any] | None:
        """
        Returns the user's cached stats only when the cache entry is younger
        than ``max_age_seconds``, otherwise None. Lets callers trust short-lived
        facts (e.g. "this user has no chunks") without disturbing the long-lived
        index data, which is drift-checked against the DB instead.
        """
        pass

    @abstractmethod
    def invalidate(self, user_id: UUID) -> None:
        """
        Invalidates a user's cached index.
        """
        pass

    @abstractmethod
    def get_cached_user_ids(self) -> builtins.set[UUID]:
        """
        Retrieves the set of user IDs currently in the cache.
        """
        pass


class SparseIndex(ABC):
    @abstractmethod
    async def index_chunks(self, user_id: UUID, chunks: list[Chunk]) -> None:
        """
        Indexes the given chunks into the sparse index for the specified user.
        """
        pass

    @abstractmethod
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
        Searches the sparse index.
        """
        pass


class SparseRetriever(ABC):
    @abstractmethod
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
        """
        Retrieves matching document chunks using sparse retrieval.
        """
        pass


class DenseRetriever(ABC):
    @abstractmethod
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
        """
        Retrieves matching document chunks using dense vector search.
        """
        pass


class FusionEngine(ABC):
    @abstractmethod
    def fuse(
        self,
        dense_results: list[RetrievedChunk],
        sparse_results: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        Fuses dense and sparse search results into a single ranked list.
        """
        pass


class MMRSelector(ABC):
    @abstractmethod
    def select(
        self,
        chunks: list[RetrievedChunk],
        top_k: int,
        mmr_lambda: float = 0.5,
        similarity_fn: Callable[[RetrievedChunk, RetrievedChunk], float] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Applies Maximum Marginal Relevance to select top_k diverse chunks.
        """
        pass


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        Reranks retrieved chunks for the given query asynchronously.
        """
        pass


class CleanupJobRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: UUID) -> CleanupJob | None:
        """
        Fetches a cleanup job by its ID.
        """
        pass

    @abstractmethod
    async def save(self, job: CleanupJob) -> CleanupJob:
        """
        Persists or updates a cleanup job.
        """
        pass

    @abstractmethod
    async def list_pending_or_failed(self) -> list[CleanupJob]:
        """
        Lists all jobs that are in PENDING or FAILED status.
        """
        pass
