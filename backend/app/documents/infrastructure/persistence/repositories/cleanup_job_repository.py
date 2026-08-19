from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import CleanupJobRepository
from app.documents.domain.models import CleanupJob
from app.documents.infrastructure.persistence.models import SQLAlchemyCleanupJob


class SQLAlchemyCleanupJobRepository(CleanupJobRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: UUID) -> CleanupJob | None:
        result = await self._db.execute(
            select(SQLAlchemyCleanupJob).where(SQLAlchemyCleanupJob.id == id)
        )
        db_job = result.scalar_one_or_none()
        if not db_job:
            return None
        return self._to_domain(db_job)

    async def save(self, job: CleanupJob) -> CleanupJob:
        result = await self._db.execute(
            select(SQLAlchemyCleanupJob).where(SQLAlchemyCleanupJob.id == job.id)
        )
        db_job = result.scalar_one_or_none()
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

        await self._db.flush()
        return self._to_domain(db_job)

    async def list_pending_or_failed(self) -> list[CleanupJob]:
        result = await self._db.execute(
            select(SQLAlchemyCleanupJob).where(
                SQLAlchemyCleanupJob.status.in_(["PENDING", "FAILED"])
            )
        )
        db_jobs = result.scalars().all()
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
