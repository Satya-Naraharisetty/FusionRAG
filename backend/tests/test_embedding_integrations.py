from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_embedding_generator, get_vector_store
from app.db.models import Base
from app.documents.domain.models import ExtractionResult

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"


@pytest.fixture(scope="function")
def emb_test_db(client):
    """
    Sets up a clean database for embedding integration tests.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = session_local()
    try:
        db.execute(text("TRUNCATE TABLE document_embeddings CASCADE;"))
        db.execute(text("TRUNCATE TABLE document_chunks CASCADE;"))
        db.execute(text("TRUNCATE TABLE documents CASCADE;"))
        db.execute(text("TRUNCATE TABLE refresh_sessions CASCADE;"))
        db.execute(text("TRUNCATE TABLE users CASCADE;"))
        db.commit()
    finally:
        db.close()

    client.app.state.db_session_factory = session_local
    yield session_local
    client.app.dependency_overrides.clear()


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
    mock_generator.batch_generate.return_value = [[0.1] * 1536]

    mock_vector_store = MagicMock()
    mock_vector_store.health.return_value = True

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="This is a single page PDF content.", page_count=1
    )

    token = get_user_token(client)

    file_payload = {"file": ("test_emb.pdf", b"dummy pdf bytes", "application/pdf")}
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
    mock_generator.batch_generate.return_value = [[0.1] * 1536]
    mock_vector_store = MagicMock()
    mock_vector_store.health.return_value = True

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="This is content for regeneration.", page_count=1
    )

    token = get_user_token(client)

    file_payload = {"file": ("test_regen.pdf", b"dummy pdf bytes", "application/pdf")}
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
    mock_generator.batch_generate.return_value = [[0.1] * 1536]
    mock_vector_store = MagicMock()
    mock_vector_store.health.return_value = True

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="Delete content.", page_count=1
    )

    token = get_user_token(client)
    file_payload = {"file": ("test_del.pdf", b"dummy pdf bytes", "application/pdf")}
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
    mock_generator.batch_generate.return_value = [[0.1] * 1536]
    mock_vector_store = MagicMock()
    mock_vector_store.health.return_value = True

    client.app.dependency_overrides[get_embedding_generator] = lambda: mock_generator
    client.app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    mock_pdf_extract.return_value = ExtractionResult(
        text="Cascade content.", page_count=1
    )

    token = get_user_token(client)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test_cascade.pdf", b"dummy pdf bytes", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    doc_id = response.json()["id"]

    del_doc_res = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_doc_res.status_code == status.HTTP_204_NO_CONTENT

    mock_vector_store.delete_document.assert_called_once_with(UUID(doc_id))
