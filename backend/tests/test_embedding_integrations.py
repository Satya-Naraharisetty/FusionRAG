from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_embedding_generator, get_vector_store
from app.db.models import Base
from app.documents.domain.models import ExtractionResult
from tests.db import TEST_DATABASE_URL


@pytest.fixture(scope="function")
async def emb_test_db(client):
    """
    Sets up a clean database for embedding integration tests.
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
            db.execute(text("DELETE FROM document_embeddings;"))
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


def get_user_token(client, email="user_emb@example.com", password="SecurePassword123!"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return response.json()["access_token"]


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_full_pipeline_ingestion_generates_embeddings(
    mock_pdf_extract, client, emb_test_db
):
    mock_generator = MagicMock()
    mock_generator.batch_generate = AsyncMock(return_value=[[0.1] * 768])

    mock_vector_store = MagicMock()
    mock_vector_store.health = AsyncMock(return_value=True)
    mock_vector_store.upsert = AsyncMock()

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="This is a single page PDF content.", page_count=1
    )

    token = get_user_token(client)

    file_payload = {
        "file": ("test_emb.pdf", b"%PDF-1.4 dummy pdf bytes", "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    doc_id = data["id"]

    status_res = client.get(
        f"/api/v1/documents/{doc_id}/embeddings/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.status_code == status.HTTP_200_OK
    status_data = status_res.json()
    assert status_data["status"] == "COMPLETED"
    assert status_data["chunks_total"] == 1
    assert status_data["embedded_chunks"] == 1
    assert status_data["failed_chunks"] == 0

    mock_generator.batch_generate.assert_called_once()
    mock_vector_store.upsert.assert_called_once()


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_embeddings_regenerate(mock_pdf_extract, client, emb_test_db):
    mock_generator = MagicMock()
    mock_generator.batch_generate = AsyncMock(return_value=[[0.1] * 768])
    mock_vector_store = MagicMock()
    mock_vector_store.health = AsyncMock(return_value=True)
    mock_vector_store.delete_document = AsyncMock()
    mock_vector_store.upsert = AsyncMock()

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="This is content for regeneration.", page_count=1
    )

    token = get_user_token(client)

    file_payload = {
        "file": ("test_regen.pdf", b"%PDF-1.4 dummy pdf bytes", "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = response.json()["id"]

    mock_generator.batch_generate.reset_mock()
    mock_vector_store.upsert.reset_mock()

    regen_res = client.post(
        f"/api/v1/documents/{doc_id}/embeddings/regenerate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert regen_res.status_code == status.HTTP_202_ACCEPTED

    mock_vector_store.delete_document.assert_called_once_with(UUID(doc_id))
    mock_generator.batch_generate.assert_called_once()
    mock_vector_store.upsert.assert_called_once()


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_embeddings_delete(mock_pdf_extract, client, emb_test_db):
    mock_generator = MagicMock()
    mock_generator.batch_generate = AsyncMock(return_value=[[0.1] * 1536])
    mock_vector_store = MagicMock()
    mock_vector_store.health = AsyncMock(return_value=True)
    mock_vector_store.upsert = AsyncMock()
    mock_vector_store.delete_document = AsyncMock()

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="Delete content.", page_count=1
    )

    token = get_user_token(client)
    file_payload = {
        "file": ("test_del.pdf", b"%PDF-1.4 dummy pdf bytes", "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        files=file_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = response.json()["id"]

    status_res = client.get(
        f"/api/v1/documents/{doc_id}/embeddings/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.json()["status"] == "COMPLETED"

    del_res = client.delete(
        f"/api/v1/documents/{doc_id}/embeddings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == status.HTTP_204_NO_CONTENT

    status_res = client.get(
        f"/api/v1/documents/{doc_id}/embeddings/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.json()["status"] == "PENDING"
    assert status_res.json()["embedded_chunks"] == 0
    mock_vector_store.delete_document.assert_called_once_with(UUID(doc_id))


@patch("app.documents.infrastructure.extractors.PDFExtractor.extract")
def test_document_deletion_cascade_clears_vectors_and_metadata(
    mock_pdf_extract, client, emb_test_db
):
    mock_generator = MagicMock()
    mock_generator.batch_generate = AsyncMock(return_value=[[0.1] * 1536])
    mock_vector_store = MagicMock()
    mock_vector_store.health = AsyncMock(return_value=True)
    mock_vector_store.upsert = AsyncMock()
    mock_vector_store.delete_document = AsyncMock()

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="Cascade content.", page_count=1
    )

    token = get_user_token(client)
    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": ("test_cascade.pdf", b"%PDF-1.4 dummy pdf bytes", "application/pdf")
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = response.json()["id"]

    del_doc_res = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_doc_res.status_code == status.HTTP_204_NO_CONTENT

    mock_vector_store.delete_document.assert_called_once_with(UUID(doc_id))
