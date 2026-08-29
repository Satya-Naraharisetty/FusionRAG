from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.chat.services.multi_agent.synthesis_agent import (
    CitationValidator,
    EvidenceAuthorizationGuard,
)
from app.core.config import settings
from app.core.queue.handlers import DocumentCutoverHandler, ValidationGateHandler
from app.core.queue.interfaces import Job
from app.documents.domain.models import (
    AuthorizedDocumentScope,
    AuthorizedDocumentVersion,
    EvidenceItem,
    EvidenceType,
    ProcessingRunState,
    generate_element_id,
    generate_entity_id,
    sanitize_cell_value,
)
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocument,
    SQLAlchemyDocumentElement,
    SQLAlchemyDocumentProcessingRun,
    SQLAlchemyGraphEntity,
)
from app.documents.infrastructure.persistence.repositories.document_element_repository import (
    SQLAlchemyDocumentElementRepository,
)
from app.documents.services.fusion import Hybrid4ChannelRRFEngine


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
    try:
        async with async_session() as session:
            try:
                await session.execute(text("SELECT 1"))
            except Exception as conn_err:
                pytest.skip(f"Live PostgreSQL database not reachable: {conn_err}")
            yield session
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_end_to_end_ingestion_cutover_and_retrieval(pg_session: AsyncSession):
    """
    Complete End-to-End Ingestion, Validation Gate, Atomic Cutover, and RAG Pipeline Integration:
    Upload -> Canonical Extraction -> Validation Gate -> Atomic Cutover -> 4-Channel RRF Retrieval -> Synthesis
    """
    user_id = uuid4()
    doc_id = uuid4()
    cfg_id = uuid4()
    run_id = uuid4()
    contract_id = "contract_phase211_v1"

    try:
        # 1. Insert User and immutable ProcessingConfigVersion
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active) VALUES (:id, :email, 'hash', 'user', true)"
            ),
            {"id": user_id, "email": f"e2e_{user_id}@test.com"},
        )
        await pg_session.execute(
            text(
                "INSERT INTO processing_config_versions (id, config_identifier, config_json) VALUES (:id, :ident, '{}')"
            ),
            {"id": cfg_id, "ident": f"config_{cfg_id}"},
        )

        # 2. Allocate Document version 1 (initially status=processing, version=1, active_version=0)
        await pg_session.execute(
            text("""
            INSERT INTO documents (id, user_id, filename, original_filename, content_type, file_size, checksum, version, active_version, scope, status, extractor_version)
            VALUES (:id, :user_id, 'annual_report.pdf', 'annual_report.pdf', 'application/pdf', 1024, :checksum, 1, 0, 'LIBRARY', 'processing', 'v1')
        """),
            {"id": doc_id, "user_id": user_id, "checksum": f"chk_{doc_id}"},
        )

        # 3. Create ProcessingRun in PROCESSING state
        run_record = SQLAlchemyDocumentProcessingRun(
            id=run_id,
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            processing_config_version_id=cfg_id,
            state="PROCESSING",
            validation_gate_passed=False,
        )
        pg_session.add(run_record)
        await pg_session.flush()

        # 4. Canonical Extraction:
        # 4a. Text Element
        elem_text_id = generate_element_id(user_id, doc_id, 1, 0)
        elem_text = SQLAlchemyDocumentElement(
            id=elem_text_id,
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            element_index=0,
            element_type="TEXT",
            content="ACME Corp reported annual revenue of $500 million in fiscal year 2024.",
            normalized_content="acme corp reported annual revenue of $500 million in fiscal year 2024.",
            metadata_json={"section": "Financial Highlights"},
            status="VALID",
        )

        # 4b. Table Element with Decimal values
        num_val, clean_val = sanitize_cell_value("500000000")
        assert num_val == Decimal("500000000")
        elem_table_id = generate_element_id(user_id, doc_id, 1, 1)
        elem_table = SQLAlchemyDocumentElement(
            id=elem_table_id,
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            element_index=1,
            element_type="TABLE",
            content="| Metric | 2024 |\n|---|---|\n| Revenue | $500M |",
            normalized_content="metric 2024 revenue 500m",
            metadata_json={"row_count": 2, "col_count": 2},
            status="VALID",
        )

        # 4c. Knowledge Graph Entity & Mention
        entity_id = generate_entity_id(user_id, "acme corp", "ORGANIZATION")
        entity = SQLAlchemyGraphEntity(
            id=entity_id,
            user_id=user_id,
            name="ACME Corp",
            normalized_name="acme corp",
            entity_type="ORGANIZATION",
            normalized_type="ORGANIZATION",
            properties_json={},
        )

        pg_session.add_all([elem_text, elem_table, entity])
        await pg_session.flush()

        # 5. Validation Gate
        factory = MockSessionFactory(pg_session)
        val_handler = ValidationGateHandler(factory)
        val_job = Job(
            task_type="VALIDATION_GATE",
            payload={
                "run_id": str(run_id),
                "expected_vector_count": 2,
                "observed_vector_count": 2,
            },
        )
        val_result = await val_handler.handle(val_job)
        assert val_result.success is True
        assert run_record.state == ProcessingRunState.READY_FOR_CUTOVER.value

        # 6. Atomic Cutover Handler (Single Transaction Assertion: affected_rows == 1)
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
        cutover_result = await cutover_handler.handle(cutover_job)
        assert cutover_result.success is True
        assert cutover_result.details.get("active_version") == 1

        # Verify Document query authority cutover in PostgreSQL
        doc_stmt = select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == doc_id)
        doc_res = await pg_session.execute(doc_stmt)
        updated_doc = doc_res.scalar_one()
        assert updated_doc.active_version == 1
        assert updated_doc.status in ("ACTIVE", "completed")

        # 7. Query Session Resolution & AuthorizedDocumentScope
        scope = AuthorizedDocumentScope(
            user_id=user_id,
            authorized_docs={
                doc_id: AuthorizedDocumentVersion(
                    active_version=1,
                    active_config_id=cfg_id,
                    active_embedding_contract_id=contract_id,
                )
            },
        )

        # 8. Sparse Search Retrieval against live PostgreSQL GIN index
        elem_repo = SQLAlchemyDocumentElementRepository(pg_session)
        sparse_hits = await elem_repo.search_sparse(
            query="ACME revenue 2024",
            user_id=user_id,
            authorized_tuples=[(doc_id, 1)],
            top_k=10,
        )
        assert len(sparse_hits) >= 1
        assert sparse_hits[0][0].document_id == doc_id
        assert sparse_hits[0][0].document_version == 1

        # 9. 4-Channel Weighted RRF Ranking
        evidence_item = EvidenceItem(
            evidence_id=uuid4(),
            evidence_type=EvidenceType.TEXT_CHUNK,
            user_id=user_id,
            document_id=doc_id,
            document_version=1,
            element_id=elem_text_id,
            content=elem_text.content,
        )
        canonical_id = (doc_id, 1, elem_text_id)
        candidate_tuple = (canonical_id, evidence_item)

        rrf_engine = Hybrid4ChannelRRFEngine()
        fused_results = rrf_engine.fuse_4_channels(
            dense_candidates=[candidate_tuple],
            sparse_candidates=[candidate_tuple],
            visual_candidates=[],
            graph_candidates=[],
            final_top_k=5,
        )
        assert len(fused_results) >= 1
        assert fused_results[0].element_id == elem_text_id

        # 10. Evidence Guard & Citation Validation Gate
        guard = EvidenceAuthorizationGuard()
        assert guard.verify(evidence_item, scope) is True

        citation_validator = CitationValidator()
        validation_res = await citation_validator.validate(
            claim_text="ACME Corp had $500 million in revenue in 2024.",
            evidence_item=evidence_item,
            scope=scope,
            guard=guard,
        )
        assert validation_res.is_valid is True

    finally:
        await pg_session.rollback()
