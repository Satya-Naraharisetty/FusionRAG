from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.documents.domain.models import Chunk, Document, Embedding, ExtractionResult


class StorageProvider(ABC):
    @abstractmethod
    def save(
        self, filename: str, content: bytes, user_id: UUID, document_id: UUID
    ) -> str:
        """
        Saves file content to storage and returns a unique key/relative path.
        """
        pass

    @abstractmethod
    def get(self, key: str) -> bytes:
        """
        Retrieves file content by unique key.
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Deletes file content from storage.
        """
        pass


class DocumentExtractor(ABC):
    @abstractmethod
    def extract(self, file_bytes: bytes) -> ExtractionResult:
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
    def get_by_id(self, id: UUID) -> Document | None:
        """
        Fetches a document by its ID.
        """
        pass

    @abstractmethod
    def get_by_id_for_update(self, id: UUID) -> Document | None:
        """
        Fetches a document by its ID and locks the row (SELECT FOR UPDATE).
        """
        pass

    @abstractmethod
    def get_by_checksum_and_user(self, checksum: str, user_id: UUID) -> Document | None:
        """
        Checks if a document with this checksum already exists for the given user.
        """
        pass

    @abstractmethod
    def list_by_user(self, user_id: UUID) -> list[Document]:
        """
        Lists all documents belonging to a user.
        """
        pass

    @abstractmethod
    def save(self, document: Document) -> Document:
        """
        Persists or updates a document.
        """
        pass

    @abstractmethod
    def delete(self, id: UUID) -> None:
        """
        Deletes a document from the database.
        """
        pass


class ChunkRepository(ABC):
    @abstractmethod
    def save_bulk(self, chunks: list[Chunk]) -> None:
        """
        Saves a list of document chunks in a bulk transaction.
        """
        pass

    @abstractmethod
    def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all chunks associated with a document.
        """
        pass

    @abstractmethod
    def list_by_document(self, document_id: UUID) -> list[Chunk]:
        """
        Retrieves all chunks associated with a document, sorted by chunk_index.
        """
        pass


class EmbeddingGenerator(ABC):
    @abstractmethod
    def generate(self, text: str) -> list[float]:
        """
        Generates a vector embedding for a single text.
        """
        pass

    @abstractmethod
    def batch_generate(self, texts: list[str]) -> list[list[float]]:
        """
        Generates vector embeddings for a list of texts in batch.
        """
        pass


class VectorStore(ABC):
    @abstractmethod
    def upsert(
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
    def delete(self, ids: list[UUID]) -> None:
        """
        Deletes vectors by their vector IDs.
        """
        pass

    @abstractmethod
    def delete_document(self, document_id: UUID) -> None:
        """
        Deletes all vectors belonging to a document ID.
        """
        pass

    @abstractmethod
    def health(self) -> bool:
        """
        Checks the health of the vector store connection.
        """
        pass


class EmbeddingRepository(ABC):
    @abstractmethod
    def save(self, embedding: Embedding) -> Embedding:
        """
        Persists or updates an embedding metadata record.
        """
        pass

    @abstractmethod
    def get_by_chunk(self, chunk_id: UUID) -> Embedding | None:
        """
        Retrieves embedding metadata for a specific chunk.
        """
        pass

    @abstractmethod
    def delete_by_document(self, document_id: UUID) -> None:
        """
        Deletes all embedding metadata associated with a document's chunks.
        """
        pass

    @abstractmethod
    def list_by_document(self, document_id: UUID) -> list[Embedding]:
        """
        Lists all embedding metadata associated with a document's chunks.
        """
        pass
