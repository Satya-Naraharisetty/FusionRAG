import logging
import pathlib
import uuid

from app.documents.domain.interfaces import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = pathlib.Path(upload_dir).resolve()

    def save(
        self, filename: str, content: bytes, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        """
        Saves file content to disk. File path format:
        data/uploads/user_{user_id}/{document_uuid}.{ext}
        """
        ext = pathlib.Path(filename).suffix.lower()

        relative_key = f"user_{user_id}/{document_id}{ext}"
        dest_path = self.upload_dir / relative_key

        # Ensure containing directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with dest_path.open("wb") as f:
            f.write(content)

        return relative_key

    def get(self, key: str) -> bytes:
        """
        Retrieves file bytes from disk by key.
        """
        file_path = self.upload_dir / key
        if not file_path.exists():
            raise FileNotFoundError(f"File not found in local storage: {key}")

        with file_path.open("rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        """
        Deletes file from disk. Cleans up parent directory if empty.
        Logs warning on failure instead of raising.
        """
        file_path = self.upload_dir / key
        if file_path.exists():
            try:
                file_path.unlink()
                # Clean up parent directory if it's now empty
                parent_dir = file_path.parent
                if parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
            except Exception as e:
                logger.warning(f"Failed to physically delete file {key}: {e}")

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
