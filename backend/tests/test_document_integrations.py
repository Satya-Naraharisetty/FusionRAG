from unittest.mock import patch

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.infrastructure.persistence.models import Base
from app.documents.domain.models import ExtractionResult

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"


@pytest.fixture(scope="function")
def doc_test_db(client):
    """
    Sets up a clean database for document tests.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE document_chunks CASCADE;"))
        db.execute(text("TRUNCATE TABLE documents CASCADE;"))
        db.execute(text("TRUNCATE TABLE refresh_sessions CASCADE;"))
        db.execute(text("TRUNCATE TABLE users CASCADE;"))
        db.commit()
    finally:
        db.close()

    client.app.state.db_session_factory = SessionLocal
    yield SessionLocal


# Helper function to register and authenticate a user
def get_user_token(client, email="user@example.com", password="SecurePassword123!"):
    # Register
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response.json()["access_token"]


# --- Document Upload & Processing Pipeline Integration Tests ---


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_upload_pdf_success(mock_pdf_extract, client, doc_test_db):
    mock_pdf_extract.return_value = ExtractionResult(
        text="This is PDF content.", page_count=2
    )

    token = get_user_token(client)

    # Upload PDF file
    file_payload = {"file": ("test.pdf", b"dummy pdf bytes", "application/pdf")}
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_filename"] == "test.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["status"] == "queued"

    # Query database state (completed due to SyncTaskQueue)
    doc_id = data["id"]
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == status.HTTP_200_OK
    get_data = get_res.json()
    assert get_data["status"] == "completed"
    assert get_data["page_count"] == 2
    assert get_data["word_count"] == 4
    assert get_data["language"] == "en"
    assert get_data["failure_reason"] is None
    assert get_data["processing_started_at"] is not None
    assert get_data["processing_completed_at"] is not None


@patch("app.documents.infrastructure.extractors.DOCXExtractor.extract")
def test_upload_docx_success(mock_docx_extract, client, doc_test_db):
    mock_docx_extract.return_value = ExtractionResult(
        text="DOCX Content paragraphs.", page_count=1
    )

    token = get_user_token(client)

    file_payload = {
        "file": (
            "test.docx",
            b"dummy docx bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_filename"] == "test.docx"
    assert data["status"] == "queued"

    # Query details
    doc_id = data["id"]
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["status"] == "completed"
    assert get_res.json()["word_count"] == 3


def test_upload_txt_success(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {
        "file": ("test.txt", b"This is clean plain text content.", "text/plain")
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_filename"] == "test.txt"
    assert data["status"] == "queued"

    # Query details
    doc_id = data["id"]
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["status"] == "completed"
    assert get_res.json()["word_count"] == 6


def test_upload_markdown_success(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {
        "file": (
            "test.md",
            b"# Markdown Header\n\nSome body text here.",
            "text/markdown",
        )
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_filename"] == "test.md"
    assert data["status"] == "queued"

    # Query details
    doc_id = data["id"]
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["status"] == "completed"
    assert get_res.json()["word_count"] == 7


# --- Validation and Error Rejections ---


def test_upload_empty_file_rejected(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert response.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


def test_upload_large_file_rejected(client, doc_test_db):
    token = get_user_token(client)

    # Exceed settings.MAX_UPLOAD_SIZE (default 25MB, let's configure a mock limit in test or just upload huge bytes)
    # To avoid writing huge payloads in memory, we can patch settings.MAX_UPLOAD_SIZE to a tiny amount
    with patch("app.core.config.settings.MAX_UPLOAD_SIZE", 10):
        file_payload = {
            "file": ("large.txt", b"This is longer than 10 bytes limit.", "text/plain")
        }
        response = client.post(
            "/api/v1/documents/upload",
            files=file_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert response.json()["error"]["code"] == "DOCUMENT_TOO_LARGE"


def test_unsupported_format_rejected(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {"file": ("photo.png", b"image bytes", "image/png")}
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert response.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_duplicate_upload_same_user_rejected(mock_pdf_extract, client, doc_test_db):
    mock_pdf_extract.return_value = ExtractionResult(text="Content", page_count=1)

    token = get_user_token(client)

    # Upload first time
    file_payload = {"file": ("file1.pdf", b"pdf content", "application/pdf")}
    client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Upload second time (duplicate upload)
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "DUPLICATE_DOCUMENT"


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_duplicate_upload_different_users_allowed(
    mock_pdf_extract, client, doc_test_db
):
    mock_pdf_extract.return_value = ExtractionResult(text="Content", page_count=1)

    token1 = get_user_token(client, email="user1@example.com")
    token2 = get_user_token(client, email="user2@example.com")

    file_payload = {"file": ("file1.pdf", b"pdf content", "application/pdf")}

    # User 1 uploads
    res1 = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res1.status_code == status.HTTP_201_CREATED

    # User 2 uploads identical file (should succeed because scoped per user)
    res2 = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res2.status_code == status.HTTP_201_CREATED


# --- Permission Isolation and Ownership tests ---


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_access_and_reprocess_unauthorized_rejected(
    mock_pdf_extract, client, doc_test_db
):
    mock_pdf_extract.return_value = ExtractionResult(text="Content", page_count=1)

    token1 = get_user_token(client, email="user1@example.com")
    token2 = get_user_token(client, email="user2@example.com")

    # User 1 uploads a file
    file_payload = {"file": ("private.pdf", b"pdf content", "application/pdf")}
    res = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token1}"},
    )
    doc_id = res.json()["id"]

    # User 2 attempts to fetch User 1's document
    res_get = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_get.status_code == status.HTTP_403_FORBIDDEN
    assert res_get.json()["error"]["code"] == "UNAUTHORIZED_DOCUMENT_ACCESS"

    # User 2 attempts to reprocess User 1's document
    res_reproc = client.post(
        f"/api/v1/documents/{doc_id}/reprocess",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_reproc.status_code == status.HTTP_403_FORBIDDEN

    # User 2 attempts to delete User 1's document
    res_del = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_del.status_code == status.HTTP_403_FORBIDDEN


# --- Reprocess & Delete Integration Tests ---


def test_reprocess_document_success(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {"file": ("test.txt", b"plain text", "text/plain")}
    res = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = res.json()["id"]

    # Reprocess
    res_reproc = client.post(
        f"/api/v1/documents/{doc_id}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res_reproc.status_code == status.HTTP_200_OK
    assert res_reproc.json()["status"] == "queued"

    # Query details to confirm it has been processed to completion
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.json()["status"] == "completed"


def test_delete_document_cascades(client, doc_test_db):
    token = get_user_token(client)

    # Upload
    file_payload = {"file": ("test.txt", b"text contents", "text/plain")}
    res = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = res.json()["id"]

    # Delete
    res_del = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_del.status_code == status.HTTP_204_NO_CONTENT

    # Try to fetch (should be 404)
    res_get = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_get.status_code == status.HTTP_404_NOT_FOUND


@patch("app.documents.infrastructure.extractors.TXTExtractor.extract")
def test_concurrent_processing_guard(mock_extract, client, doc_test_db):
    import threading
    import uuid

    # We want Thread A to block in extraction
    event_started = threading.Event()
    event_proceed = threading.Event()

    def blocking_extract(file_bytes):
        event_started.set()
        event_proceed.wait(timeout=5.0)  # Wait for main thread signal
        return ExtractionResult(text="extracted plain text content", page_count=1)

    mock_extract.side_effect = blocking_extract

    # Let's get the document processing service instance
    db_session = doc_test_db()

    # Let's register a user in DB first
    client.post(
        "/api/v1/auth/register",
        json={"email": "concur@example.com", "password": "SecurePassword123!"},
    )
    # Get user
    user_record = db_session.execute(
        text("SELECT id FROM users WHERE email='concur@example.com'")
    ).first()
    user_id = user_record[0]

    # Create a document record directly in QUEUED state
    doc_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, status, extractor_version, created_at, updated_at) "
            "VALUES (:id, :user_id, 'file.txt', 'file.txt', 'text/plain', 10, 'sum', 'queued', 'v1', NOW(), NOW())"
        ),
        {"id": doc_id, "user_id": user_id},
    )
    db_session.commit()
    db_session.close()

    # Set up thread worker
    results = []

    def run_pipeline(name):
        from unittest.mock import MagicMock

        engine = create_engine(TEST_DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        try:
            from app.auth.infrastructure.providers import (
                SQLAlchemyUnitOfWork,
                SystemTimeProvider,
            )
            from app.documents.infrastructure.extractors import ExtractorFactory
            from app.documents.infrastructure.persistence.repositories.chunk_repository import (
                SQLAlchemyChunkRepository,
            )
            from app.documents.infrastructure.persistence.repositories.document_repository import (
                SQLAlchemyDocumentRepository,
            )
            from app.documents.services.chunking import ChunkingService
            from app.documents.services.document_processing_service import (
                DocumentProcessingService,
            )
            from app.documents.services.metadata_extractor import MetadataExtractor
            from app.documents.services.text_cleaner import TextCleaner

            # Mock storage provider get to return dummy text
            storage = MagicMock()
            storage.get.return_value = b"some file content"

            proc_service = DocumentProcessingService(
                document_repo=SQLAlchemyDocumentRepository(db),
                chunk_repo=SQLAlchemyChunkRepository(db),
                storage_provider=storage,
                extractor_factory=ExtractorFactory(),
                text_cleaner=TextCleaner(),
                metadata_extractor=MetadataExtractor(),
                chunking_service=ChunkingService(),
                uow=SQLAlchemyUnitOfWork(db),
                time_provider=SystemTimeProvider(),
            )

            proc_service.process_document(doc_id)
            results.append((name, "success", None))
        except Exception as e:
            results.append((name, "error", str(e)))
        finally:
            db.close()

    # Start Thread A
    t_a = threading.Thread(target=run_pipeline, args=("ThreadA",))
    t_a.start()

    # Wait until Thread A reaches the blocking extractor
    event_started.wait(timeout=5.0)

    # Start Thread B concurrently
    t_b = threading.Thread(target=run_pipeline, args=("ThreadB",))
    t_b.start()
    t_b.join()  # Thread B should finish instantly because status is PROCESSING

    # Allow Thread A to continue and finish
    event_proceed.set()
    t_a.join()

    # Verify results
    assert len(results) == 2
    thread_a_res = [r for r in results if r[0] == "ThreadA"][0]
    thread_b_res = [r for r in results if r[0] == "ThreadB"][0]

    if thread_a_res[1] == "error":
        raise RuntimeError(f"Thread A failed with: {thread_a_res[2]}")
    if thread_b_res[1] == "error":
        raise RuntimeError(f"Thread B failed with: {thread_b_res[2]}")

    assert thread_a_res[1] == "success"
    assert thread_b_res[1] == "success"
