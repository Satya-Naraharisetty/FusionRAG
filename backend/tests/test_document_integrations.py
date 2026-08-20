import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.db.models import Base
from app.documents.domain.models import ExtractionResult
from tests.db import TEST_DATABASE_URL


@pytest.fixture(scope="function")
async def doc_test_db(client):
    """
    Sets up a clean database for document tests.
    """
    sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(async_url, poolclass=NullPool)
    try:
        Base.metadata.create_all(bind=sync_engine)

        sync_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=sync_engine
        )

        db = sync_session_local()
        try:
            db.execute(text("DELETE FROM document_chunks;"))
            db.execute(text("DELETE FROM documents;"))
            db.execute(text("DELETE FROM refresh_sessions;"))
            db.execute(text("DELETE FROM users;"))
            db.commit()
        finally:
            db.close()

        async_session_local = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        client.app.state.db_session_factory = async_session_local

        from app.api.dependencies import get_db

        http_engine = create_async_engine(async_url, poolclass=NullPool)
        http_session_factory = async_sessionmaker(
            bind=http_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        async def _http_get_db():
            async with http_session_factory() as session:
                yield session

        client.app.dependency_overrides[get_db] = _http_get_db
        yield sync_session_local
        client.app.dependency_overrides.clear()
    finally:
        sync_engine.dispose()


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


def _insert_conversation(db, user_id):
    """
    Inserts a conversation row owned by ``user_id`` and returns its id.
    (The upload endpoint requires the conversation to exist and belong to the
    caller — FK to ``conversations`` plus the ownership check.)
    """
    conversation_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO conversations "
            "(id, user_id, title, state, settings, metadata, version, created_at, updated_at, last_message_at) "
            "VALUES (:id, :user_id, 'Chat', 'active', '{}'::json, '{}'::json, 1, NOW(), NOW(), NOW())"
        ),
        {"id": conversation_id, "user_id": user_id},
    )
    db.commit()
    return conversation_id


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

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "DOCUMENT_CORRUPTED"


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
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert response.json()["error"]["code"] == "DOCUMENT_TOO_LARGE"


def test_unsupported_format_rejected(client, doc_test_db):
    token = get_user_token(client)

    file_payload = {"file": ("archive.zip", b"zip bytes", "application/zip")}
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


def test_conversation_scoped_documents_isolated_from_global_list(client, doc_test_db):
    """
    Chat-scoped documents (uploaded with a conversation_id) must be listable
    via ?conversation_id= but must never appear in the user's global document
    list — and vice versa.
    """
    token = get_user_token(client)

    db_session = doc_test_db()
    try:
        user_id = db_session.execute(
            text("SELECT id FROM users WHERE email='user@example.com'")
        ).first()[0]
        conversation_id = _insert_conversation(db_session, user_id)
    finally:
        db_session.close()

    headers = {"Authorization": f"Bearer {token}"}

    # A global document (Documents section)…
    res_global = client.post(
        "/api/v1/documents/upload",
        files={"file": ("global.txt", b"global content", "text/plain")},
        headers=headers,
    )
    assert res_global.status_code == status.HTTP_201_CREATED
    global_id = res_global.json()["id"]

    # …and a chat-scoped document (attached in the conversation).
    res_scoped = client.post(
        f"/api/v1/conversations/{conversation_id}/documents",
        files={"file": ("chat.txt", b"chat content", "text/plain")},
        headers=headers,
    )
    assert res_scoped.status_code == status.HTTP_201_CREATED
    scoped_id = res_scoped.json()["id"]
    assert res_scoped.json()["conversation_id"] == str(conversation_id)

    # Global list: only the global document.
    res_list = client.get("/api/v1/documents", headers=headers)
    assert res_list.status_code == status.HTTP_200_OK
    listed_ids = [d["id"] for d in res_list.json()]
    assert global_id in listed_ids
    assert scoped_id not in listed_ids

    # Conversation-scoped list: only the chat document.
    res_conv = client.get(
        f"/api/v1/conversations/{conversation_id}/documents",
        headers=headers,
    )
    assert res_conv.status_code == status.HTTP_200_OK
    conv_ids = [d["id"] for d in res_conv.json()]
    assert scoped_id in conv_ids
    assert global_id not in conv_ids

    # Deleting the chat-scoped document removes it from the conversation list.
    res_del = client.delete(f"/api/v1/documents/{scoped_id}", headers=headers)
    assert res_del.status_code == status.HTTP_204_NO_CONTENT
    res_conv_after = client.get(
        f"/api/v1/conversations/{conversation_id}/documents",
        headers=headers,
    )
    assert res_conv_after.json() == []


def test_upload_to_foreign_conversation_rejected(client, doc_test_db):
    """
    Chat-scoped uploads must verify the conversation belongs to the caller.
    Attaching a file into another user's conversation (403) or referencing an
    unknown conversation (404) is rejected — otherwise any authenticated user
    could pollute someone else's chat with documents.
    """
    token_owner = get_user_token(client, email="owner@example.com")
    token_attacker = get_user_token(client, email="attacker@example.com")

    db_session = doc_test_db()
    try:
        owner_id = db_session.execute(
            text("SELECT id FROM users WHERE email='owner@example.com'")
        ).first()[0]
        foreign_conversation_id = _insert_conversation(db_session, owner_id)
    finally:
        db_session.close()

    # A different user cannot attach a document into owner's conversation.
    res_foreign = client.post(
        f"/api/v1/conversations/{foreign_conversation_id}/documents",
        files={"file": ("evil.txt", b"evil content", "text/plain")},
        headers={"Authorization": f"Bearer {token_attacker}"},
    )
    assert res_foreign.status_code == status.HTTP_403_FORBIDDEN

    # An unknown conversation id is rejected too.
    res_unknown = client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/documents",
        files={"file": ("ghost.txt", b"ghost content", "text/plain")},
        headers={"Authorization": f"Bearer {token_attacker}"},
    )
    assert res_unknown.status_code == status.HTTP_404_NOT_FOUND

    # The owner can still attach into their own conversation.
    res_own = client.post(
        f"/api/v1/conversations/{foreign_conversation_id}/documents",
        files={"file": ("mine.txt", b"my content", "text/plain")},
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert res_own.status_code == status.HTTP_201_CREATED


def test_delete_conversation_removes_scoped_docs_but_keeps_global(client, doc_test_db):
    """
    Deleting a conversation must cascade away its chat-scoped documents —
    including their chunks and embedding metadata — while the user's global
    documents (and their chunks/embeddings) survive untouched. This is the
    lifecycle contract of the two-tier model: chat attachments die with the
    chat, library uploads persist.
    """
    token = get_user_token(client)

    db_session = doc_test_db()
    try:
        user_id = db_session.execute(
            text("SELECT id FROM users WHERE email='user@example.com'")
        ).first()[0]
        conversation_id = _insert_conversation(db_session, user_id)
    finally:
        db_session.close()

    headers = {"Authorization": f"Bearer {token}"}

    # A global (library) document and a chat-scoped attachment. Both ingest to
    # completion — chunks and embeddings — before we delete anything.
    res_global = client.post(
        "/api/v1/documents/upload",
        files={"file": ("global.txt", b"global content", "text/plain")},
        headers=headers,
    )
    assert res_global.status_code == status.HTTP_201_CREATED
    global_id = res_global.json()["id"]

    res_scoped = client.post(
        f"/api/v1/conversations/{conversation_id}/documents",
        files={"file": ("chat.txt", b"chat content", "text/plain")},
        headers=headers,
    )
    assert res_scoped.status_code == status.HTTP_201_CREATED
    scoped_id = res_scoped.json()["id"]

    def _count(table, doc_id):
        db = doc_test_db()
        try:
            if table == "document_chunks":
                return db.execute(
                    text(
                        "SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"
                    ),
                    {"id": doc_id},
                ).first()[0]
            return db.execute(
                text(
                    "SELECT COUNT(*) FROM document_embeddings e "
                    "JOIN document_chunks c ON c.id = e.chunk_id "
                    "WHERE c.document_id = :id"
                ),
                {"id": doc_id},
            ).first()[0]
        finally:
            db.close()

    # Sanity: both documents fully ingested (chunks + embeddings exist).
    assert _count("document_chunks", global_id) > 0
    assert _count("document_chunks", scoped_id) > 0
    assert _count("document_embeddings", global_id) > 0
    assert _count("document_embeddings", scoped_id) > 0

    # Delete the conversation — the chat-scoped document must die with it.
    res_del = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert res_del.status_code == status.HTTP_204_NO_CONTENT

    # Chat-scoped document: gone from the API and its conversation list.
    assert (
        client.get(f"/api/v1/documents/{scoped_id}", headers=headers).status_code
        == status.HTTP_404_NOT_FOUND
    )
    res_conv = client.get(
        f"/api/v1/conversations/{conversation_id}/documents",
        headers=headers,
    )
    assert res_conv.json() == []

    # …and its chunks + embedding metadata were cascaded away.
    assert _count("document_chunks", scoped_id) == 0
    assert _count("document_embeddings", scoped_id) == 0

    # Global document: fully intact — API, library list, chunks, embeddings.
    res_global_get = client.get(f"/api/v1/documents/{global_id}", headers=headers)
    assert res_global_get.status_code == status.HTTP_200_OK
    res_list = client.get("/api/v1/documents", headers=headers)
    assert global_id in [d["id"] for d in res_list.json()]
    assert scoped_id not in [d["id"] for d in res_list.json()]
    assert _count("document_chunks", global_id) > 0
    assert _count("document_embeddings", global_id) > 0


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


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.TXTExtractor.extract")
async def test_concurrent_processing_guard(mock_extract, client, doc_test_db):
    import asyncio
    import uuid

    # We want Task A to block in extraction
    event_started = asyncio.Event()
    event_proceed = asyncio.Event()

    async def blocking_extract(file_bytes):
        event_started.set()
        await event_proceed.wait()
        return ExtractionResult(text="extracted plain text content", page_count=1)

    mock_extract.side_effect = blocking_extract

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

    results = []

    async def run_pipeline(name):
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

        async_url = TEST_DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
        async_engine = create_async_engine(async_url)
        async_session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        async with async_session_factory() as db:
            try:
                storage = MagicMock()
                storage.get = AsyncMock(return_value=b"some file content")

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

                await proc_service.process_document(doc_id)
                results.append((name, "success", None))
            except Exception as e:
                results.append((name, "error", str(e)))
            finally:
                await async_engine.dispose()

    # Start Task A
    task_a = asyncio.create_task(run_pipeline("TaskA"))

    # Wait until Task A reaches the blocking extractor
    await event_started.wait()

    # Start Task B concurrently
    task_b = asyncio.create_task(run_pipeline("TaskB"))
    await task_b  # Task B should finish instantly because status is PROCESSING

    # Allow Task A to continue and finish
    event_proceed.set()
    await task_a

    # Verify results
    assert len(results) == 2
    task_a_res = [r for r in results if r[0] == "TaskA"][0]
    task_b_res = [r for r in results if r[0] == "TaskB"][0]

    if task_a_res[1] == "error":
        raise RuntimeError(f"Task A failed with: {task_a_res[2]}")
    if task_b_res[1] == "error":
        raise RuntimeError(f"Task B failed with: {task_b_res[2]}")

    assert task_a_res[1] == "success"
    assert task_b_res[1] == "success"


@pytest.mark.asyncio
async def test_document_processing_invalidates_index_cache(client, doc_test_db):
    """
    Successfully ingesting a document must invalidate the user's entry in the
    shared index cache. A chat request made before the upload cached the
    "no chunks" determination (count == 0); after processing commits chunks,
    that entry must be gone so the next chat message re-checks the DB and
    serves the freshly indexed knowledge instead of a general answer.
    """
    import uuid

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
    from app.documents.services.index_cache import InMemoryIndexCache
    from app.documents.services.metadata_extractor import MetadataExtractor
    from app.documents.services.text_cleaner import TextCleaner

    db_session = doc_test_db()
    client.post(
        "/api/v1/auth/register",
        json={"email": "cache@example.com", "password": "SecurePassword123!"},
    )
    user_record = db_session.execute(
        text("SELECT id FROM users WHERE email='cache@example.com'")
    ).first()
    user_id = user_record[0]

    # A QUEUED document owned by the user (as the upload endpoint would create).
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

    # Shared index cache pre-seeded exactly as a chat request for this
    # document-less user would have left it.
    cache = InMemoryIndexCache()
    cache.set(user_id, index_data=None, stats={"count": 0, "max_created_at": None})
    assert cache.get_stats(user_id) == {"count": 0, "max_created_at": None}

    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(async_url)
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with async_session_factory() as db:
        try:
            storage = MagicMock()
            storage.get = AsyncMock(return_value=b"uploaded plain text content")

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
                index_cache=cache,
            )

            await proc_service.process_document(doc_id)
        finally:
            await async_engine.dispose()

    # The cached "no chunks" flag must be invalidated after ingestion so the
    # next chat message re-checks the DB and sees the new chunks.
    assert cache.get_stats(user_id) is None
    assert cache.get(user_id) is None

    # Sanity: the pipeline really did commit chunks for the user.
    sync_engine = create_engine(TEST_DATABASE_URL)
    session_factory = sessionmaker(bind=sync_engine)
    verify_db = session_factory()
    try:
        row = verify_db.execute(
            text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
            {"id": doc_id},
        ).first()
        assert row[0] > 0
    finally:
        verify_db.close()
        sync_engine.dispose()


# --- Document Replacement Integration Tests ---


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
@patch("app.documents.infrastructure.extractors.DOCXExtractor.extract")
def test_replace_document_e2e_lifecycle(
    mock_docx_extract, mock_pdf_extract, client, doc_test_db
):
    mock_pdf_extract.return_value = ExtractionResult(
        text="Original PDF text version one.", page_count=1
    )
    mock_docx_extract.return_value = ExtractionResult(
        text="Replaced DOCX text version two with different contents.", page_count=2
    )

    token = get_user_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initial Upload
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("original.pdf", b"pdf content v1", "application/pdf")},
        headers=headers,
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_data = upload_res.json()
    doc_id = doc_data["id"]
    assert doc_data["original_filename"] == "original.pdf"
    assert doc_data["scope"] == "LIBRARY"
    assert doc_data["conversation_id"] is None

    # Wait / verify chunks created for original
    db = doc_test_db()
    try:
        old_chunks = db.execute(
            text("SELECT id, text FROM document_chunks WHERE document_id = :id"),
            {"id": doc_id},
        ).fetchall()
        assert len(old_chunks) > 0
        old_chunk_ids = {str(c[0]) for c in old_chunks}
    finally:
        db.close()

    # 2. Replace Document Content via PUT /documents/{id}
    replace_res = client.put(
        f"/api/v1/documents/{doc_id}",
        files={
            "file": (
                "updated.docx",
                b"docx content v2 new bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=headers,
    )
    assert replace_res.status_code == status.HTTP_200_OK
    updated_doc = replace_res.json()
    assert updated_doc["id"] == doc_id
    assert updated_doc["original_filename"] == "updated.docx"
    assert updated_doc["scope"] == "LIBRARY"
    assert updated_doc["conversation_id"] is None

    # 3. Verify in DB that new chunks exist and old chunk IDs are gone
    db = doc_test_db()
    try:
        new_chunks = db.execute(
            text("SELECT id, text FROM document_chunks WHERE document_id = :id"),
            {"id": doc_id},
        ).fetchall()
        assert len(new_chunks) > 0
        new_chunk_ids = {str(c[0]) for c in new_chunks}
        # Invariant: Old chunk IDs are replaced by new chunk IDs
        assert not old_chunk_ids.intersection(new_chunk_ids)

        # Verify document table metadata is synchronized
        doc_row = db.execute(
            text(
                "SELECT original_filename, content_type, file_size FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        ).first()
        assert doc_row[0] == "updated.docx"
        assert (
            doc_row[1]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert doc_row[2] == len(b"docx content v2 new bytes")
    finally:
        db.close()


def test_replace_document_same_checksum_is_noop(client, doc_test_db):
    token = get_user_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload document
    file_bytes = b"plain text document identical"
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc.txt", file_bytes, "text/plain")},
        headers=headers,
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["id"]

    # PUT with exact same file bytes
    replace_res = client.put(
        f"/api/v1/documents/{doc_id}",
        files={"file": ("doc.txt", file_bytes, "text/plain")},
        headers=headers,
    )
    assert replace_res.status_code == status.HTTP_200_OK
    assert replace_res.json()["id"] == doc_id


def test_replace_document_duplicate_other_doc_rejected(client, doc_test_db):
    token = get_user_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload Doc 1
    res1 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc1.txt", b"content of doc 1", "text/plain")},
        headers=headers,
    )
    assert res1.status_code == status.HTTP_201_CREATED

    # Upload Doc 2
    res2 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("doc2.txt", b"content of doc 2", "text/plain")},
        headers=headers,
    )
    assert res2.status_code == status.HTTP_201_CREATED
    doc2_id = res2.json()["id"]

    # Replace Doc 2 with Doc 1's content
    replace_res = client.put(
        f"/api/v1/documents/{doc2_id}",
        files={"file": ("doc2.txt", b"content of doc 1", "text/plain")},
        headers=headers,
    )
    assert replace_res.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
    )


def test_replace_document_unauthorized_user_rejected(client, doc_test_db):
    user1_token = get_user_token(client, email="owner@example.com")
    user2_token = get_user_token(client, email="attacker@example.com")

    # User 1 uploads document
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("secret.txt", b"owner secrets", "text/plain")},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.json()["id"]

    # User 2 attempts to replace User 1's document
    replace_res = client.put(
        f"/api/v1/documents/{doc_id}",
        files={"file": ("hacked.txt", b"hacked content", "text/plain")},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert replace_res.status_code in (
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    )
