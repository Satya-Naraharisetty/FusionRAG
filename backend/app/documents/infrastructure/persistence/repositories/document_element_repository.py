from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import DocumentElementRepository
from app.documents.domain.models import DocumentElement, ElementStatus, ElementType
from app.documents.infrastructure.persistence.models import SQLAlchemyDocumentElement


class SQLAlchemyDocumentElementRepository(DocumentElementRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_bulk(self, elements: list[DocumentElement]) -> None:
        if not elements:
            return
        db_elements = [
            SQLAlchemyDocumentElement(
                id=e.id,
                user_id=e.user_id,
                document_id=e.document_id,
                document_version=e.document_version,
                element_index=e.element_index,
                element_type=e.element_type.value
                if hasattr(e.element_type, "value")
                else str(e.element_type),
                parent_element_id=e.parent_element_id,
                content=e.content,
                normalized_content=e.normalized_content,
                page_number=e.page_number,
                bounding_box_json=e.bounding_box,
                metadata_json=e.metadata,
                status=e.status.value if hasattr(e.status, "value") else str(e.status),
                created_at=e.created_at,
            )
            for e in elements
        ]
        self._db.add_all(db_elements)
        await self._db.flush()

    async def get_by_id(
        self, user_id: UUID, document_id: UUID, document_version: int, element_id: UUID
    ) -> DocumentElement | None:
        stmt = select(SQLAlchemyDocumentElement).where(
            SQLAlchemyDocumentElement.user_id == user_id,
            SQLAlchemyDocumentElement.document_id == document_id,
            SQLAlchemyDocumentElement.document_version == document_version,
            SQLAlchemyDocumentElement.id == element_id,
        )
        result = await self._db.execute(stmt)
        db_elem = result.scalar_one_or_none()
        if not db_elem:
            return None
        return self._to_domain(db_elem)

    async def list_by_version(
        self, user_id: UUID, document_id: UUID, document_version: int
    ) -> list[DocumentElement]:
        stmt = (
            select(SQLAlchemyDocumentElement)
            .where(
                SQLAlchemyDocumentElement.user_id == user_id,
                SQLAlchemyDocumentElement.document_id == document_id,
                SQLAlchemyDocumentElement.document_version == document_version,
            )
            .order_by(SQLAlchemyDocumentElement.element_index.asc())
        )
        result = await self._db.execute(stmt)
        db_elems = result.scalars().all()
        return [self._to_domain(e) for e in db_elems]

    async def search_sparse(
        self,
        query: str,
        user_id: UUID,
        authorized_tuples: list[tuple[UUID, int]],
        top_k: int = 50,
    ) -> list[tuple[DocumentElement, float]]:
        if not authorized_tuples or not query.strip():
            return []

        # Check database dialect
        bind = self._db.bind
        dialect_name = bind.dialect.name if bind else "postgresql"

        if dialect_name == "postgresql":
            # PostgreSQL full-text search with pre-filtering
            ts_query = func.websearch_to_tsquery("english", query)
            ts_vector = func.coalesce(
                SQLAlchemyDocumentElement.search_vector,
                func.to_tsvector(
                    "english",
                    func.coalesce(SQLAlchemyDocumentElement.normalized_content, ""),
                ),
            )
            rank_col = func.ts_rank_cd(ts_vector, ts_query).label("rank")

            tuple_conditions = [
                and_(
                    SQLAlchemyDocumentElement.document_id == doc_id,
                    SQLAlchemyDocumentElement.document_version == doc_ver,
                )
                for doc_id, doc_ver in authorized_tuples
            ]

            stmt = (
                select(SQLAlchemyDocumentElement, rank_col)
                .where(
                    SQLAlchemyDocumentElement.user_id == user_id,
                    SQLAlchemyDocumentElement.status == "VALID",
                    ts_vector.op("@@")(ts_query),
                    tuple_conditions[0]
                    if len(tuple_conditions) == 1
                    else func.or_(*tuple_conditions),
                )
                .order_by(rank_col.desc(), SQLAlchemyDocumentElement.id.asc())
                .limit(top_k)
            )
            result = await self._db.execute(stmt)
            rows = result.all()
            return [(self._to_domain(elem), float(rank)) for elem, rank in rows]
        else:
            # SQLite / Fallback for unit testing
            tuple_conditions = [
                and_(
                    SQLAlchemyDocumentElement.document_id == doc_id,
                    SQLAlchemyDocumentElement.document_version == doc_ver,
                )
                for doc_id, doc_ver in authorized_tuples
            ]
            terms = [t.strip().lower() for t in query.split() if t.strip()]
            like_conditions = [
                func.lower(SQLAlchemyDocumentElement.normalized_content).contains(term)
                for term in terms
            ]

            stmt = (
                select(SQLAlchemyDocumentElement)
                .where(
                    SQLAlchemyDocumentElement.user_id == user_id,
                    SQLAlchemyDocumentElement.status == "VALID",
                    func.or_(*tuple_conditions),
                    func.or_(*like_conditions) if like_conditions else text("1=1"),
                )
                .limit(top_k)
            )
            result = await self._db.execute(stmt)
            elems = result.scalars().all()
            scored: list[tuple[DocumentElement, float]] = []
            for elem in elems:
                content_lower = elem.normalized_content.lower()
                matches = sum(1 for term in terms if term in content_lower)
                score = matches / max(1, len(terms))
                scored.append((self._to_domain(elem), score))
            scored.sort(key=lambda x: (-x[1], str(x[0].id)))
            return scored[:top_k]

    def _to_domain(self, db_elem: SQLAlchemyDocumentElement) -> DocumentElement:
        return DocumentElement(
            id=db_elem.id,
            user_id=db_elem.user_id,
            document_id=db_elem.document_id,
            document_version=db_elem.document_version,
            element_index=db_elem.element_index,
            element_type=ElementType(db_elem.element_type),
            parent_element_id=db_elem.parent_element_id,
            content=db_elem.content,
            normalized_content=db_elem.normalized_content,
            page_number=db_elem.page_number,
            bounding_box=db_elem.bounding_box_json,
            metadata=db_elem.metadata_json or {},
            status=ElementStatus(db_elem.status),
            created_at=db_elem.created_at,
        )
