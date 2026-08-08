import logging
import pathlib
import uuid

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.documents.domain.interfaces import StorageProvider
from app.documents.infrastructure.persistence.models import SQLAlchemyDocumentFile

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


class DatabaseStorageProvider(StorageProvider):
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(
        self, filename: str, content: bytes, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        ext = pathlib.Path(filename).suffix.lower()
        key = f"user_{user_id}/{document_id}{ext}"

        doc_file = SQLAlchemyDocumentFile(key=key, content=content)
        self.db.add(doc_file)
        self.db.commit()

        return key

    def get(self, key: str) -> bytes:
        doc_file = self.db.query(SQLAlchemyDocumentFile).filter_by(key=key).first()
        if not doc_file:
            raise FileNotFoundError(f"File not found in database storage: {key}")
        return doc_file.content

    def delete(self, key: str) -> None:
        doc_file = self.db.query(SQLAlchemyDocumentFile).filter_by(key=key).first()
        if doc_file:
            self.db.delete(doc_file)
            self.db.commit()
        else:
            logger.warning(f"File {key} not found for deletion in database.")

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        return f"http://localhost:8000/api/v1/documents/upload-local/{key}"

    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        return f"http://localhost:8000/api/v1/documents/download-local/{key}"


class S3StorageProvider(StorageProvider):
    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name

        # Build client arguments dict dynamically to omit None/empty values
        client_kwargs = {}
        if aws_access_key_id:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if region_name:
            client_kwargs["region_name"] = region_name
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        self.s3_client = boto3.client("s3", **client_kwargs)

    def verify_connection(self) -> None:
        """
        Verify that the bucket exists and we can access it (read-only checks).
        Uses head_bucket() and list_objects_v2(MaxKeys=1).
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            raise RuntimeError(
                f"S3 bucket '{self.bucket_name}' not found or insufficient access permissions: {e}"
            ) from e

        try:
            self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)
        except ClientError as e:
            raise RuntimeError(
                f"Failed to list objects in S3 bucket '{self.bucket_name}': {e}"
            ) from e

    def verify_write_access(self) -> None:
        """
        Verify that we have write/delete permissions on the bucket.
        """
        test_key = f"startup_write_test_{uuid.uuid4()}.txt"
        test_content = b"Verification test content."
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=test_key, Body=test_content
            )
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=test_key)
        except ClientError as e:
            raise RuntimeError(
                f"Insufficient write permissions in S3 bucket '{self.bucket_name}': {e}"
            ) from e

    def save(
        self, filename: str, content: bytes, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        ext = pathlib.Path(filename).suffix.lower()
        key = f"user_{user_id}/{document_id}{ext}"
        try:
            self.s3_client.put_object(Bucket=self.bucket_name, Key=key, Body=content)
            return key
        except ClientError as e:
            logger.error(f"S3 save failed for key {key}: {e}")
            raise OSError(f"Failed to save file to S3: {e}") from e

    def get(self, key: str) -> bytes:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found in S3: {key}")
            logger.error(f"S3 get failed for key {key}: {e}")
            raise OSError(f"Failed to retrieve file from S3: {e}") from e

    def delete(self, key: str) -> None:
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        except ClientError as e:
            logger.warning(f"Failed to delete file {key} from S3: {e}")

    def generate_presigned_upload_url(self, key: str, expires_in: int = 3600) -> str:
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned upload URL: {e}")
            raise OSError(f"Presigned URL generation failed: {e}") from e

    def generate_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned download URL: {e}")
            raise OSError(f"Presigned URL generation failed: {e}") from e
