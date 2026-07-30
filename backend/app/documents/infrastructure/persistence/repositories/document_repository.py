from uuid import UUID

from sqlalchemy.orm import Session

from app.documents.domain.interfaces import DocumentRepository
from app.documents.domain.models import Document, DocumentStatus
from app.documents.infrastructure.persistence.models import SQLAlchemyDocument


class SQLAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, id: UUID) -> Document | None:
        db_doc = (
            self._db.query(SQLAlchemyDocument)
            .filter(SQLAlchemyDocument.id == id)
            .first()
        )
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    def get_by_id_for_update(self, id: UUID) -> Document | None:
        db_doc = (
            self._db.query(SQLAlchemyDocument)
            .filter(SQLAlchemyDocument.id == id)
            .with_for_update()
            .first()
        )
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    def get_by_checksum_and_user(self, checksum: str, user_id: UUID) -> Document | None:
        db_doc = (
            self._db.query(SQLAlchemyDocument)
            .filter(
                SQLAlchemyDocument.checksum == checksum,
                SQLAlchemyDocument.user_id == user_id,
            )
            .first()
        )
        if not db_doc:
            return None
        return self._to_domain(db_doc)

    def list_by_user(self, user_id: UUID) -> list[Document]:
        db_docs = (
            self._db.query(SQLAlchemyDocument)
            .filter(SQLAlchemyDocument.user_id == user_id)
            .order_by(SQLAlchemyDocument.created_at.desc())
            .all()
        )
        return [self._to_domain(d) for d in db_docs]

    def save(self, document: Document) -> Document:
        db_doc = (
            self._db.query(SQLAlchemyDocument)
            .filter(SQLAlchemyDocument.id == document.id)
            .first()
        )
        if not db_doc:
            db_doc = SQLAlchemyDocument(
                id=document.id,
                user_id=document.user_id,
                filename=document.filename,
                original_filename=document.original_filename,
                content_type=document.content_type,
                file_size=document.file_size,
                checksum=document.checksum,
                status=document.status.value,
                extractor_version=document.extractor_version,
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
            db_doc.status = document.status.value
            db_doc.extractor_version = document.extractor_version
            db_doc.failure_reason = document.failure_reason
            db_doc.page_count = document.page_count
            db_doc.word_count = document.word_count
            db_doc.language = document.language
            db_doc.updated_at = document.updated_at
            db_doc.processing_started_at = document.processing_started_at
            db_doc.processing_completed_at = document.processing_completed_at

        self._db.flush()
        return self._to_domain(db_doc)

    def delete(self, id: UUID) -> None:
        db_doc = (
            self._db.query(SQLAlchemyDocument)
            .filter(SQLAlchemyDocument.id == id)
            .first()
        )
        if db_doc:
            self._db.delete(db_doc)
            self._db.flush()

    def _to_domain(self, db_doc: SQLAlchemyDocument) -> Document:
        return Document(
            id=db_doc.id,
            user_id=db_doc.user_id,
            filename=db_doc.filename,
            original_filename=db_doc.original_filename,
            content_type=db_doc.content_type,
            file_size=db_doc.file_size,
            checksum=db_doc.checksum,
            status=DocumentStatus(db_doc.status),
            extractor_version=db_doc.extractor_version,
            failure_reason=db_doc.failure_reason,
            page_count=db_doc.page_count,
            word_count=db_doc.word_count,
            language=db_doc.language,
            created_at=db_doc.created_at,
            updated_at=db_doc.updated_at,
            processing_started_at=db_doc.processing_started_at,
            processing_completed_at=db_doc.processing_completed_at,
        )
