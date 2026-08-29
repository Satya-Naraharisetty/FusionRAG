from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocumentElement,
    SQLAlchemyDocumentProcessingRun,
)
from app.documents.infrastructure.persistence.repositories.document_element_repository import (
    SQLAlchemyDocumentElementRepository,
)


@pytest.fixture
async def pg_session():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    if "pgbouncer=" in url.lower():
        parsed = urlparse(url)
        qsl = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "pgbouncer"]
        url = urlunparse(parsed._replace(query=urlencode(qsl)))

    engine = create_async_engine(
        url,
        connect_args={"statement_cache_size": 0},
        poolclass=NullPool,
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_postgres_composite_fk_enforcement(pg_session: AsyncSession):
    """Test that PostgreSQL strictly enforces composite tenant FK (user_id, document_id) -> documents(user_id, id)."""
    user_a = uuid4()
    user_b = uuid4()
    doc_a = uuid4()

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_a, "email": f"user_a_{user_a}@test.com"},
        )
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_b, "email": f"user_b_{user_b}@test.com"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'test.pdf', 'test.pdf', 'application/pdf', 100, :checksum, 1, 1, 'LIBRARY', 'completed', 'v1')
        """),
            {"id": doc_a, "user_id": user_a, "checksum": f"chk_{doc_a}"},
        )

        # 1. Valid insert with matching (user_a, doc_a)
        elem_valid = SQLAlchemyDocumentElement(
            id=uuid4(),
            user_id=user_a,
            document_id=doc_a,
            document_version=1,
            element_index=0,
            element_type="TEXT",
            content="Valid content for User A",
            normalized_content="valid content for user a",
            metadata_json={},
            status="VALID",
        )
        pg_session.add(elem_valid)
        await pg_session.flush()

        # 2. Invalid insert with cross-user mismatch: element belongs to user_b, but document belongs to user_a
        elem_invalid = SQLAlchemyDocumentElement(
            id=uuid4(),
            user_id=user_b,  # Mismatch!
            document_id=doc_a,
            document_version=1,
            element_index=1,
            element_type="TEXT",
            content="Mismatched tenant element",
            normalized_content="mismatched tenant element",
            metadata_json={},
            status="VALID",
        )
        pg_session.add(elem_invalid)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
    finally:
        await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_check_constraints(pg_session: AsyncSession):
    """Test CHECK constraints (no self-loops, version >= active_version, active_version >= 0)."""
    user_id = uuid4()
    doc_id = uuid4()
    entity_a = uuid4()

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"user_{user_id}@test.com"},
        )

        # 1. Test ck_documents_version_ge_active violation (version 0 < active_version 1)
        with pytest.raises(IntegrityError):
            async with pg_session.begin_nested():
                await pg_session.execute(
                    text("""
                    INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
                    VALUES (:id, :user_id, 'bad.pdf', 'bad.pdf', 'application/pdf', 100, :checksum, 0, 1, 'LIBRARY', 'completed', 'v1')
                """),
                    {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
                )
                await pg_session.flush()

        # 2. Test ck_graph_no_self_loops violation (source_entity_id == target_entity_id)
        await pg_session.execute(
            text("""
            INSERT INTO graph_entities (id, user_id, name, normalized_name, entity_type, normalized_type, properties)
            VALUES (:id, :user_id, 'SelfEntity', 'selfentity', 'CONCEPT', 'CONCEPT', '{}')
        """),
            {"id": entity_a, "user_id": user_id},
        )

        with pytest.raises(IntegrityError):
            async with pg_session.begin_nested():
                await pg_session.execute(
                    text("""
                    INSERT INTO graph_relationships (id, user_id, source_entity_id, target_entity_id, relation_type, normalized_relation_type, weight)
                    VALUES (:id, :user_id, :entity_id, :entity_id, 'SELF_REL', 'SELF_REL', 1.0)
                """),
                    {"id": uuid4(), "user_id": user_id, "entity_id": entity_a},
                )
                await pg_session.flush()
    finally:
        await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_partial_unique_index_active_run(pg_session: AsyncSession):
    """Test partial unique index: at most one ACTIVE processing run per document."""
    user_id = uuid4()
    doc_id = uuid4()
    cfg_id = uuid4()

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"user_{user_id}@test.com"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO processing_config_versions (id, config_identifier, config_json)
            VALUES (:id, :ident, '{}')
        """),
            {"id": cfg_id, "ident": f"cfg_{cfg_id}"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'doc.pdf', 'doc.pdf', 'application/pdf', 100, :checksum, 2, 1, 'LIBRARY', 'completed', 'v1')
        """),
            {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
        )

        # 1. Insert first ACTIVE processing run
        run_1 = SQLAlchemyDocumentProcessingRun(
            id=uuid4(),
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            processing_config_version_id=cfg_id,
            state="ACTIVE",
            validation_gate_passed=True,
        )
        pg_session.add(run_1)
        await pg_session.flush()

        # 2. Insert second ACTIVE processing run for the same document -> must fail partial unique index
        run_2 = SQLAlchemyDocumentProcessingRun(
            id=uuid4(),
            user_id=user_id,
            document_id=doc_id,
            document_version=2,
            processing_config_version_id=cfg_id,
            state="ACTIVE",
            validation_gate_passed=True,
        )
        pg_session.add(run_2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
    finally:
        await pg_session.rollback()


@pytest.mark.asyncio
async def test_live_postgres_gin_search_and_version_isolation(pg_session: AsyncSession):
    """Test GIN full-text search index and version isolation on live PostgreSQL."""
    user_id = uuid4()
    doc_id = uuid4()

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"user_{user_id}@test.com"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'doc.pdf', 'doc.pdf', 'application/pdf', 100, :checksum, 2, 1, 'LIBRARY', 'completed', 'v1')
        """),
            {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
        )

        # Insert element for version 1
        elem_v1 = SQLAlchemyDocumentElement(
            id=uuid4(),
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            element_index=0,
            element_type="TEXT",
            content="Quantum computing encryption algorithms in 2024",
            normalized_content="quantum computing encryption algorithms in 2024",
            metadata_json={},
            status="VALID",
        )
        # Insert element for version 2
        elem_v2 = SQLAlchemyDocumentElement(
            id=uuid4(),
            user_id=user_id,
            document_id=doc_id,
            document_version=2,
            element_index=0,
            element_type="TEXT",
            content="Classical computing algorithms in 1990",
            normalized_content="classical computing algorithms in 1990",
            metadata_json={},
            status="VALID",
        )
        pg_session.add_all([elem_v1, elem_v2])
        await pg_session.flush()

        repo = SQLAlchemyDocumentElementRepository(pg_session)

        # Query with authorized tuple for version 1
        results_v1 = await repo.search_sparse(
            query="quantum encryption",
            user_id=user_id,
            authorized_tuples=[(doc_id, 1)],
            top_k=10,
        )
        assert len(results_v1) >= 1
        assert results_v1[0][0].document_version == 1

        # Query with authorized tuple for version 2 -> quantum is not in v2
        results_v2 = await repo.search_sparse(
            query="quantum encryption",
            user_id=user_id,
            authorized_tuples=[(doc_id, 2)],
            top_k=10,
        )
        assert len(results_v2) == 0
    finally:
        await pg_session.rollback()
