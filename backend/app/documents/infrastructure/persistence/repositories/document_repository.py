from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import DocumentRepository
from app.documents.domain.models import Document, DocumentScope, DocumentStatus
from app.documents.infrastructure.persistence.models import SQLAlchemyDocument


class SQLAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: UUID) -> Document | None:
        result = await self._db.execute(
            select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == id)
        )
        db_doc = result.scalar_one_or_none()
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    async def get_by_id_for_update(self, id: UUID) -> Document | None:
        result = await self._db.execute(
            select(SQLAlchemyDocument)
            .where(SQLAlchemyDocument.id == id)
            .with_for_update()
        )
        db_doc = result.scalar_one_or_none()
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    async def get_by_checksum_and_user(
        self, checksum: str, user_id: UUID
    ) -> Document | None:
        result = await self._db.execute(
            select(SQLAlchemyDocument).where(
                SQLAlchemyDocument.checksum == checksum,
                SQLAlchemyDocument.user_id == user_id,
            )
        )
        db_doc = result.scalar_one_or_none()
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    async def list_by_user(self, user_id: UUID) -> list[Document]:
        result = await self._db.execute(
            select(SQLAlchemyDocument)
            .where(SQLAlchemyDocument.user_id == user_id)
            .order_by(SQLAlchemyDocument.created_at.desc())
        )
        db_docs = result.scalars().all()
        return [self._to_domain(d) for d in db_docs]

    async def list_by_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> list[Document]:
        result = await self._db.execute(
            select(SQLAlchemyDocument)
            .where(
                SQLAlchemyDocument.conversation_id == conversation_id,
                SQLAlchemyDocument.user_id == user_id,
            )
            .order_by(SQLAlchemyDocument.created_at.desc())
        )
        db_docs = result.scalars().all()
        return [self._to_domain(d) for d in db_docs]

    async def save(self, document: Document) -> Document:
        result = await self._db.execute(
            select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == document.id)
        )
        db_doc = result.scalar_one_or_none()
        if not db_doc:
            db_doc = SQLAlchemyDocument(
                id=document.id,
                user_id=document.user_id,
                scope=document.scope.value
                if hasattr(document.scope, "value")
                else str(document.scope),
                conversation_id=document.conversation_id,
                filename=document.filename,
                original_filename=document.original_filename,
                content_type=document.content_type,
                file_size=document.file_size,
                checksum=document.checksum,
                status=document.status.value,
                extractor_version=document.extractor_version,
                version=document.version,
                active_version=document.active_version,
                active_processing_config_version_id=document.active_processing_config_version_id,
                failure_reason=document.failure_reason,
                page_count=document.page_count,
                word_count=document.word_count,
                language=document.language,
                created_at=document.created_at,
                updated_at=document.updated_at,
                processing_started_at=document.processing_started_at,
                processing_completed_at=document.processing_completed_at,
            )
            self._db.add(db_doc)
        else:
            db_doc.filename = document.filename
            db_doc.original_filename = document.original_filename
            db_doc.content_type = document.content_type
            db_doc.file_size = document.file_size
            db_doc.checksum = document.checksum
            db_doc.status = document.status.value
            db_doc.extractor_version = document.extractor_version
            db_doc.version = document.version
            db_doc.active_version = document.active_version
            db_doc.active_processing_config_version_id = (
                document.active_processing_config_version_id
            )
            db_doc.failure_reason = document.failure_reason
            db_doc.page_count = document.page_count
            db_doc.word_count = document.word_count
            db_doc.language = document.language
            db_doc.updated_at = document.updated_at
            db_doc.processing_started_at = document.processing_started_at
            db_doc.processing_completed_at = document.processing_completed_at

        await self._db.flush()
        await self._db.refresh(db_doc)
        return self._to_domain(db_doc)

    async def delete(self, id: UUID) -> None:
        result = await self._db.execute(
            select(SQLAlchemyDocument).where(SQLAlchemyDocument.id == id)
        )
        db_doc = result.scalar_one_or_none()
        if db_doc:
            await self._db.delete(db_doc)
            await self._db.flush()

    def _to_domain(self, db_doc: SQLAlchemyDocument) -> Document:
        return Document(
            id=db_doc.id,
            user_id=db_doc.user_id,
            scope=DocumentScope(db_doc.scope),
            conversation_id=db_doc.conversation_id,
            filename=db_doc.filename,
            original_filename=db_doc.original_filename,
            content_type=db_doc.content_type,
            file_size=db_doc.file_size,
            checksum=db_doc.checksum,
            status=DocumentStatus(db_doc.status),
            extractor_version=db_doc.extractor_version,
            version=db_doc.version,
            active_version=db_doc.active_version,
            active_processing_config_version_id=db_doc.active_processing_config_version_id,
            failure_reason=db_doc.failure_reason,
            page_count=db_doc.page_count,
            word_count=db_doc.word_count,
            language=db_doc.language,
            created_at=db_doc.created_at,
            updated_at=db_doc.updated_at,
            processing_started_at=db_doc.processing_started_at,
            processing_completed_at=db_doc.processing_completed_at,
        )
