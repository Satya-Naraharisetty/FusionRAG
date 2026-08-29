import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.domain.interfaces import ProcessingRunRepository
from app.documents.domain.models import (
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingRun,
    ProcessingRunState,
)
from app.documents.infrastructure.persistence.models import (
    SQLAlchemyDocumentProcessingJob,
    SQLAlchemyDocumentProcessingRun,
)


class SQLAlchemyProcessingRunRepository(ProcessingRunRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_run(self, run: ProcessingRun) -> ProcessingRun:
        db_run = SQLAlchemyDocumentProcessingRun(
            id=run.id,
            user_id=run.user_id,
            document_id=run.document_id,
            document_version=run.document_version,
            processing_config_version_id=run.processing_config_version_id,
            state=run.state.value if hasattr(run.state, "value") else str(run.state),
            validation_gate_passed=run.validation_gate_passed,
            created_at=run.created_at,
            completed_at=run.completed_at,
            superseded_at=run.superseded_at,
        )
        self._db.add(db_run)
        await self._db.flush()
        await self._db.refresh(db_run)
        return self._run_to_domain(db_run)

    async def get_run_by_id(self, run_id: UUID) -> ProcessingRun | None:
        stmt = select(SQLAlchemyDocumentProcessingRun).where(
            SQLAlchemyDocumentProcessingRun.id == run_id
        )
        result = await self._db.execute(stmt)
        db_run = result.scalar_one_or_none()
        if not db_run:
            return None
        return self._run_to_domain(db_run)

    async def get_active_run_for_document(
        self, document_id: UUID
    ) -> ProcessingRun | None:
        stmt = select(SQLAlchemyDocumentProcessingRun).where(
            SQLAlchemyDocumentProcessingRun.document_id == document_id,
            SQLAlchemyDocumentProcessingRun.state == "ACTIVE",
        )
        result = await self._db.execute(stmt)
        db_run = result.scalar_one_or_none()
        if not db_run:
            return None
        return self._run_to_domain(db_run)

    async def update_run_state(
        self,
        run_id: UUID,
        state: str,
        validation_gate_passed: bool | None = None,
    ) -> None:
        stmt = select(SQLAlchemyDocumentProcessingRun).where(
            SQLAlchemyDocumentProcessingRun.id == run_id
        )
        result = await self._db.execute(stmt)
        db_run = result.scalar_one_or_none()
        if db_run:
            db_run.state = state
            if validation_gate_passed is not None:
                db_run.validation_gate_passed = validation_gate_passed
            if state in ("ACTIVE", "FAILED", "SUPERSEDED"):
                db_run.completed_at = datetime.now(UTC)
            if state == "SUPERSEDED":
                db_run.superseded_at = datetime.now(UTC)
            await self._db.flush()

    async def create_jobs(self, jobs: list[ProcessingJob]) -> None:
        if not jobs:
            return
        db_jobs = [
            SQLAlchemyDocumentProcessingJob(
                id=j.id,
                run_id=j.run_id,
                user_id=j.user_id,
                document_id=j.document_id,
                document_version=j.document_version,
                job_type=j.job_type,
                idempotency_key=j.idempotency_key,
                status=j.status.value if hasattr(j.status, "value") else str(j.status),
                lease_token=j.lease_token,
                lease_expires_at=j.lease_expires_at,
                heartbeat_at=j.heartbeat_at,
                attempts=j.attempts,
                last_error=j.last_error,
                created_at=j.created_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ]
        self._db.add_all(db_jobs)
        await self._db.flush()

    async def lease_job(
        self, job_type: str, worker_id: str, lease_duration_seconds: int = 60
    ) -> ProcessingJob | None:
        now = datetime.now(UTC)
        stmt = (
            select(SQLAlchemyDocumentProcessingJob)
            .where(
                SQLAlchemyDocumentProcessingJob.job_type == job_type,
                SQLAlchemyDocumentProcessingJob.status == "PENDING",
            )
            .order_by(SQLAlchemyDocumentProcessingJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._db.execute(stmt)
        db_job = result.scalar_one_or_none()
        if not db_job:
            return None

        lease_token = f"{worker_id}:{uuid.uuid4()}"
        db_job.status = "LEASED"
        db_job.lease_token = lease_token
        db_job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
        db_job.heartbeat_at = now
        db_job.attempts += 1
        await self._db.flush()
        await self._db.refresh(db_job)
        return self._job_to_domain(db_job)

    async def update_job_fenced(
        self,
        job_id: UUID,
        lease_token: str,
        status: str,
        last_error: str | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        stmt = (
            update(SQLAlchemyDocumentProcessingJob)
            .where(
                SQLAlchemyDocumentProcessingJob.id == job_id,
                SQLAlchemyDocumentProcessingJob.lease_token == lease_token,
                SQLAlchemyDocumentProcessingJob.lease_expires_at > now,
            )
            .values(
                status=status,
                last_error=last_error,
                completed_at=now if status in ("COMPLETED", "FAILED") else None,
            )
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        rowcount = getattr(result, "rowcount", 0) or 0
        return rowcount > 0

    def _run_to_domain(self, db_run: SQLAlchemyDocumentProcessingRun) -> ProcessingRun:
        return ProcessingRun(
            id=db_run.id,
            user_id=db_run.user_id,
            document_id=db_run.document_id,
            document_version=db_run.document_version,
            processing_config_version_id=db_run.processing_config_version_id,
            state=ProcessingRunState(db_run.state),
            validation_gate_passed=db_run.validation_gate_passed,
            created_at=db_run.created_at,
            completed_at=db_run.completed_at,
            superseded_at=db_run.superseded_at,
        )

    def _job_to_domain(self, db_job: SQLAlchemyDocumentProcessingJob) -> ProcessingJob:
        return ProcessingJob(
            id=db_job.id,
            run_id=db_job.run_id,
            user_id=db_job.user_id,
            document_id=db_job.document_id,
            document_version=db_job.document_version,
            job_type=db_job.job_type,
            idempotency_key=db_job.idempotency_key,
            status=ProcessingJobStatus(db_job.status),
            lease_token=db_job.lease_token,
            lease_expires_at=db_job.lease_expires_at,
            heartbeat_at=db_job.heartbeat_at,
            attempts=db_job.attempts,
            last_error=db_job.last_error,
            created_at=db_job.created_at,
            completed_at=db_job.completed_at,
        )
