import asyncio
import logging
import pathlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import StorageProvider
from app.documents.infrastructure.persistence.models import SQLAlchemyDocumentFile

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = pathlib.Path(upload_dir).resolve()

    async def save(
        self, filename: str, content: bytes, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        """
        Saves file content to disk inside a thread pool.
        """
        ext = pathlib.Path(filename).suffix.lower()
        relative_key = f"user_{user_id}/{document_id}{ext}"
        dest_path = self.upload_dir / relative_key

        def _write():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with dest_path.open("wb") as f:
                f.write(content)

        await asyncio.to_thread(_write)
        return relative_key

    async def get(self, key: str) -> bytes:
        """
        Retrieves file bytes from disk by key inside a thread pool.
        """
        file_path = self.upload_dir / key

        def _read():
            if not file_path.exists():
                raise FileNotFoundError(f"File not found in local storage: {key}")
            with file_path.open("rb") as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def delete(self, key: str) -> None:
        """
        Deletes file from disk inside a thread pool.
        """
        file_path = self.upload_dir / key

        def _delete():
            if file_path.exists():
                try:
                    file_path.unlink()
                    parent_dir = file_path.parent
                    if parent_dir.exists() and not any(parent_dir.iterdir()):
                        parent_dir.rmdir()
                except Exception as e:
                    logger.warning(f"Failed to physically delete file {key}: {e}")

        await asyncio.to_thread(_delete)

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generates a direct upload URL. Returns local endpoint URL.
        """
        return f"http://localhost:8000/api/v1/documents/upload-local/{key}"

    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generates a direct download URL. Returns local endpoint URL.
        """
        return f"http://localhost:8000/api/v1/documents/download-local/{key}"


class DatabaseStorageProvider(StorageProvider):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(
        self, filename: str, content: bytes, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        ext = pathlib.Path(filename).suffix.lower()
        key = f"user_{user_id}/{document_id}{ext}"

        doc_file = SQLAlchemyDocumentFile(key=key, content=content)
        self.db.add(doc_file)
        await self.db.commit()

        return key

    async def get(self, key: str) -> bytes:
        result = await self.db.execute(
            select(SQLAlchemyDocumentFile).where(SQLAlchemyDocumentFile.key == key)
        )
        doc_file = result.scalar_one_or_none()
        if not doc_file:
            raise FileNotFoundError(f"File not found in database storage: {key}")
        return doc_file.content

    async def delete(self, key: str) -> None:
        result = await self.db.execute(
            select(SQLAlchemyDocumentFile).where(SQLAlchemyDocumentFile.key == key)
        )
        doc_file = result.scalar_one_or_none()
        if doc_file:
            await self.db.delete(doc_file)
            await self.db.commit()
        else:
            logger.warning(f"File {key} not found for deletion in database.")

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        return f"http://localhost:8000/api/v1/documents/upload-local/{key}"

    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"http://localhost:8000/api/v1/documents/download-local/{key}"
