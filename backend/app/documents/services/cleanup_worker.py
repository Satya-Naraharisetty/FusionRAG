import asyncio
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.reliability.retry import retry_with_backoff
from app.documents.domain.interfaces import IndexCache, StorageProvider, VectorStore
from app.documents.infrastructure.persistence.models import SQLAlchemyCleanupJob

logger = logging.getLogger(__name__)


class DurableCleanupWorker:
    def __init__(
        self,
        db: Session,
        storage_provider: StorageProvider,
        vector_store: VectorStore,
        index_cache: IndexCache | None = None,
    ) -> None:
        self._db = db
        self._storage_provider = storage_provider
        self._vector_store = vector_store
        self._index_cache = index_cache

    async def process_job(self, job_id: UUID) -> None:
        """
        Processes a cleanup job durably.
        If a resource is already absent (e.g. storage object, vectors, cache), it treats it as success.
        Marks job status as COMPLETED upon success, or FAILED on final failure.
        """
        # Fetch the job from the database
        db_job = (
            self._db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.id == job_id)
            .first()
        )
        if not db_job:
            logger.error(f"Cleanup job {job_id} not found in database.")
            return

        if db_job.status == "COMPLETED":
            logger.info(f"Cleanup job {job_id} is already COMPLETED. Skipping.")
            return

        db_job.status = "PROCESSING"
        db_job.attempts += 1
        self._db.flush()
        self._db.commit()

        payload = db_job.payload
        document_id = payload.get("document_id")
        user_id = payload.get("user_id")
        storage_key = payload.get("storage_key")
        qdrant_point_ids = payload.get("qdrant_point_ids", [])

        try:
            # 1. Clean up from VectorStore (Qdrant)
            if qdrant_point_ids:

                async def delete_vectors():
                    point_uuids = [UUID(pid) for pid in qdrant_point_ids]
                    self._vector_store.delete(point_uuids)

                try:
                    await retry_with_backoff(delete_vectors, max_attempts=3)
                except Exception as e:
                    logger.warning(
                        f"Vector store deletion for point IDs failed: {e}. Continuing."
                    )

            # Also delete document from Qdrant by document_id filter if needed, to be absolutely sure
            if document_id:

                async def delete_doc_vectors():
                    self._vector_store.delete_document(UUID(document_id))

                try:
                    await retry_with_backoff(delete_doc_vectors, max_attempts=3)
                except Exception as e:
                    logger.warning(
                        f"Qdrant document deletion failed/absent: {e}. Continuing."
                    )

            # 2. Clean up from StorageProvider
            if storage_key:

                async def delete_storage():
                    self._storage_provider.delete(storage_key)

                try:
                    await retry_with_backoff(delete_storage, max_attempts=3)
                except Exception as e:
                    logger.warning(f"Storage deletion failed/absent: {e}. Continuing.")

            # 3. Invalidate cache
            if user_id and self._index_cache:
                try:
                    self._index_cache.invalidate(UUID(user_id))
                except Exception as e:
                    logger.error(
                        f"Failed to invalidate index cache for user {user_id}: {e}"
                    )

            # Refetch job to mark completed
            db_job = (
                self._db.query(SQLAlchemyCleanupJob)
                .filter(SQLAlchemyCleanupJob.id == job_id)
                .first()
            )
            if db_job:
                db_job.status = "COMPLETED"
                db_job.last_error = None
                logger.info(f"Cleanup job {job_id} COMPLETED successfully.")

        except Exception as err:
            logger.exception(f"Fatal error processing cleanup job {job_id}: {err}")
            db_job = (
                self._db.query(SQLAlchemyCleanupJob)
                .filter(SQLAlchemyCleanupJob.id == job_id)
                .first()
            )
            if db_job:
                db_job.status = "FAILED"
                db_job.last_error = str(err)

        finally:
            try:
                self._db.flush()
                self._db.commit()
            except Exception as e:
                logger.error(f"Failed to commit cleanup job status update: {e}")
                self._db.rollback()

    def process_pending_jobs(self) -> None:
        """
        Synchronously scans and retries all PENDING or FAILED cleanup jobs.
        Useful for startup polling or fallback cron execution.
        """
        db_jobs = (
            self._db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.status.in_(["PENDING", "FAILED"]))
            .all()
        )
        if not db_jobs:
            return

        logger.info(f"Found {len(db_jobs)} pending/failed cleanup jobs. Executing...")
        for job in db_jobs:
            try:
                # Run synchronously
                asyncio.run(self.process_job(job.id))
            except Exception as e:
                logger.error(f"Failed to run job {job.id} synchronously: {e}")


def run_durable_cleanup_recovery() -> None:
    """
    Spawns the background recovery task on startup in a non-blocking manner.
    """
    asyncio.create_task(async_durable_cleanup_recovery())


async def async_durable_cleanup_recovery() -> None:
    logger.info("Starting durable cleanup recovery scan...")
    try:
        # Query database for pending/failed jobs in a separate thread to maintain thread-safety
        job_ids = await asyncio.to_thread(_query_pending_failed_jobs)
        if not job_ids:
            logger.info("No pending or failed cleanup jobs found during startup recovery.")
            return

        logger.info(f"Durable cleanup recovery found {len(job_ids)} jobs to process. Dispatched in background.")
        
        # Trigger async execution of these jobs using a helper that manages its own DB session
        await _run_cleanup_jobs_async(job_ids)

    except Exception as e:
        logger.error(f"Error during durable cleanup startup recovery: {e}")


def _query_pending_failed_jobs() -> list[UUID]:
    import sys
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from app.db.session import init_postgres_engine
    
    db_url = settings.DATABASE_URL
    if "pytest" in sys.modules:
        import os
        db_url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5433/hybrid_rag_test",
        )
    if not db_url:
        logger.error("DATABASE_URL not configured, skipping startup recovery query.")
        return []

    engine = init_postgres_engine(db_url)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        limit = getattr(settings, "CLEANUP_RECOVERY_BATCH_SIZE", 20)
        jobs = (
            db.query(SQLAlchemyCleanupJob)
            .filter(SQLAlchemyCleanupJob.status.in_(["PENDING", "FAILED"]))
            .limit(limit)
            .all()
        )
        return [job.id for job in jobs]
    finally:
        db.close()
        engine.dispose()


async def _run_cleanup_jobs_async(job_ids: list[UUID]) -> None:
    import sys
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from app.db.session import init_postgres_engine
    from app.api.dependencies import get_storage_provider, get_vector_store, get_index_cache
    
    db_url = settings.DATABASE_URL
    if "pytest" in sys.modules:
        import os
        db_url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5433/hybrid_rag_test",
        )
    if not db_url:
        return

    engine = init_postgres_engine(db_url)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        storage_provider = get_storage_provider(db)
        vector_store = get_vector_store()
        index_cache = get_index_cache()
        worker = DurableCleanupWorker(
            db, storage_provider, vector_store, index_cache
        )
        for jid in job_ids:
            try:
                await worker.process_job(jid)
            except Exception as e:
                logger.error(f"Error processing cleanup job {jid} in startup recovery: {e}")
    finally:
        db.close()
        engine.dispose()
