from uuid import UUID

from sqlalchemy.orm import Session

from app.documents.domain.interfaces import CleanupJobRepository
from app.documents.domain.models import CleanupJob
from app.documents.infrastructure.persistence.models import SQLAlchemyCleanupJob


class SQLAlchemyCleanupJobRepository(CleanupJobRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, id: UUID) -> CleanupJob | None:
        db_job = (
            self._db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.id == id)
            .first()
        )
        if not db_job:
            return None
        return self._to_domain(db_job)

    def save(self, job: CleanupJob) -> CleanupJob:
        db_job = (
            self._db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.id == job.id)
            .first()
        )
        if not db_job:
            db_job = SQLAlchemyCleanupJob(
                id=job.id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                payload=job.payload,
                status=job.status,
                attempts=job.attempts,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            self._db.add(db_job)
        else:
            db_job.status = job.status
            db_job.attempts = job.attempts
            db_job.last_error = job.last_error
            db_job.updated_at = job.updated_at
            db_job.payload = job.payload

        self._db.flush()
        return self._to_domain(db_job)

    def list_pending_or_failed(self) -> list[CleanupJob]:
        db_jobs = (
            self._db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.status.in_(["PENDING", "FAILED"]))
            .all()
        )
        return [self._to_domain(j) for j in db_jobs]

    def _to_domain(self, db_job: SQLAlchemyCleanupJob) -> CleanupJob:
        return CleanupJob(
            id=db_job.id,
            resource_type=db_job.resource_type,
            resource_id=db_job.resource_id,
            payload=db_job.payload,
            status=db_job.status,
            attempts=db_job.attempts,
            last_error=db_job.last_error,
            created_at=db_job.created_at,
            updated_at=db_job.updated_at,
        )
