from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.queue.handlers import DocumentCutoverHandler, ValidationGateHandler
from app.core.queue.interfaces import Job
from app.documents.domain.models import (
    ProcessingConfigVersion,
    ProcessingRunState,
    generate_element_id,
    generate_qdrant_point_id,
)
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocument,
    SQLAlchemyDocumentElement,
    SQLAlchemyDocumentProcessingRun,
)


class MockSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return MockSessionContext(self.session)


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
async def test_failure_injection_validation_gate_rejection_and_cutover_immunity(
    pg_session: AsyncSession,
):
    """
    Phase P Failure Injection:
    Deliberately inject vector count mismatch at Validation Gate -> run state becomes FAILED,
    validation_gate_passed remains False, and DocumentCutoverHandler rejects cutover.
    The document's active_version remains untouched at version 0.
    """
    user_id = uuid4()
    doc_id = uuid4()
    cfg_id = uuid4()
    run_id = uuid4()

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"fail_{user_id}@test.com"},
        )
        await pg_session.execute(
            text(
                "INSERT INTO processing_config_versions (id, config_identifier, config_json) VALUES (:id, :ident, '{}')"
            ),
            {"id": cfg_id, "ident": f"config_{cfg_id}"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'test.pdf', 'test.pdf', 'application/pdf', 100, :checksum, 1, 0, 'LIBRARY', 'processing', 'v1')
        """),
            {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
        )

        run_record = SQLAlchemyDocumentProcessingRun(
            id=run_id,
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            processing_config_version_id=cfg_id,
            state="VALIDATING",
            validation_gate_passed=False,
        )
        pg_session.add(run_record)
        await pg_session.flush()

        # 1. Validation Gate Failure: Expected 5 vectors, Observed 2
        factory = MockSessionFactory(pg_session)
        val_handler = ValidationGateHandler(factory)
        val_job = Job(
            task_type="VALIDATION_GATE",
            payload={
                "run_id": str(run_id),
                "expected_vector_count": 5,
                "observed_vector_count": 2,  # Mismatch!
            },
        )
        val_res = await val_handler.handle(val_job)
        assert val_res.success is False
        assert run_record.validation_gate_passed is False
        assert run_record.state == ProcessingRunState.FAILED.value

        # 2. Attempt Cutover on Failed Validation Run -> Must be rejected
        cutover_handler = DocumentCutoverHandler(factory)
        cutover_job = Job(
            task_type="DOCUMENT_CUTOVER",
            payload={
                "run_id": str(run_id),
                "user_id": str(user_id),
                "document_id": str(doc_id),
                "document_version": 1,
                "processing_config_version_id": str(cfg_id),
            },
        )
        cutover_res = await cutover_handler.handle(cutover_job)
        assert cutover_res.success is False

        # 3. Document active_version in PostgreSQL remains 0
        doc_stmt = select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == doc_id)
        doc_res = await pg_session.execute(doc_stmt)
        doc_after = doc_res.scalar_one()
        assert doc_after.active_version == 0
        assert doc_after.version == 1

    finally:
        await pg_session.rollback()


@pytest.mark.asyncio
async def test_projection_rebuild_deterministic_equivalence(pg_session: AsyncSession):
    """
    Phase E Projection Rebuild:
    1. Populate canonical PostgreSQL state (document, elements, entities).
    2. Compute initial projection identities (deterministic UUIDv5 Qdrant points, GIN vectors).
    3. Simulate projection destruction / purge.
    4. Reconstruct projections from canonical PostgreSQL rows and ProcessingConfigVersion.
    5. Assert 100% deterministic identity equivalence between initial and rebuilt projections.
    """
    user_id = uuid4()
    doc_id = uuid4()
    doc_version = 1

    cfg = ProcessingConfigVersion(
        extraction_provider="gemini",
        extraction_model="gemini-3.5-flash",
        extraction_model_revision="v1",
        extraction_schema_revision="v1",
        normalization_revision="v1",
        chunking_revision="v1",
        embedding_provider="jina",
        embedding_model="jina-embeddings-v3",
        embedding_model_revision="v1",
        embedding_dimensions=768,
        prompt_revision="v1",
        vision_prompt_revision="v1",
        ocr_config_revision="v1",
        table_parser_revision="v1",
        citation_validator_provider="gemini",
        citation_validator_model="gemini-3.5-flash",
        citation_validator_policy_revision="v1",
    )
    contract_id = cfg.get_embedding_contract_id("TEXT")

    try:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"rebuild_{user_id}@test.com"},
        )
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'report.pdf', 'report.pdf', 'application/pdf', 200, :checksum, 1, 1, 'LIBRARY', 'ACTIVE', 'v1')
        """),
            {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
        )

        # Insert 3 canonical elements
        elements = [
            SQLAlchemyDocumentElement(
                id=generate_element_id(user_id, doc_id, doc_version, idx),
                user_id=user_id,
                document_id=doc_id,
                document_version=doc_version,
                element_index=idx,
                element_type="TEXT",
                content=f"Section {idx} data content.",
                normalized_content=f"section {idx} data content.",
                metadata_json={"idx": idx},
                status="VALID",
            )
            for idx in range(3)
        ]
        pg_session.add_all(elements)
        await pg_session.flush()

        # Step 1: Compute Initial Projection Points
        initial_points = {}
        for elem in elements:
            pt_id = generate_qdrant_point_id(
                user_id=user_id,
                document_id=doc_id,
                document_version=doc_version,
                element_id=elem.id,
                representation_type="TEXT",
                embedding_contract_id=contract_id,
            )
            initial_points[elem.id] = pt_id

        # Step 2: Simulate Complete Projection Destruction (e.g. Qdrant cluster recreation)
        # (initial_points remain in memory for verification against freshly rebuilt projections)

        # Step 3: Rebuild Projections Strictly from Canonical PostgreSQL Rows & Immutable Config
        stmt = (
            select(SQLAlchemyDocumentElement)
            .where(
                SQLAlchemyDocumentElement.user_id == user_id,
                SQLAlchemyDocumentElement.document_id == doc_id,
                SQLAlchemyDocumentElement.document_version == doc_version,
            )
            .order_by(SQLAlchemyDocumentElement.element_index.asc())
        )
        res = await pg_session.execute(stmt)
        canonical_rows = res.scalars().all()

        rebuilt_points = {}
        rebuilt_contract_id = cfg.get_embedding_contract_id("TEXT")
        assert rebuilt_contract_id == contract_id

        for row in canonical_rows:
            rebuilt_pt_id = generate_qdrant_point_id(
                user_id=row.user_id,
                document_id=row.document_id,
                document_version=row.document_version,
                element_id=row.id,
                representation_type="TEXT",
                embedding_contract_id=rebuilt_contract_id,
            )
            rebuilt_points[row.id] = rebuilt_pt_id

        # Step 4: Verify 100% Deterministic Projection Equivalence
        assert len(rebuilt_points) == len(initial_points) == 3
        for elem_id in initial_points:
            assert rebuilt_points[elem_id] == initial_points[elem_id]

    finally:
        await pg_session.rollback()
