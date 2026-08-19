import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.infrastructure.persistence.models import SQLAlchemyDocument

logger = logging.getLogger(__name__)


class ResourceQuotaService:
    def __init__(self, db: AsyncSession, redis_client: Any | None = None) -> None:
        self.db = db
        self._redis = redis_client

    async def verify_upload_quota(
        self, user_id: UUID, new_file_size_bytes: int
    ) -> bool:
        """
        Verify if the user is within their document upload quotas.
        Checks total uploaded document count and aggregate storage size limits.
        """
        try:
            # 1. Enforce max document count (e.g., 50 documents limit)
            doc_count_result = await self.db.scalar(
                select(func.count())
                .select_from(SQLAlchemyDocument)
                .where(SQLAlchemyDocument.user_id == user_id)
            )
            doc_count = doc_count_result or 0
            if doc_count >= 50:
                logger.warning(
                    f"User {user_id} upload rejected: document limit (50) reached."
                )
                return False

            # 2. Enforce max storage size limit (e.g., 500 MB limit)
            total_size_result = await self.db.scalar(
                select(func.sum(SQLAlchemyDocument.file_size)).where(
                    SQLAlchemyDocument.user_id == user_id
                )
            )
            total_size = total_size_result or 0
            max_bytes = 500 * 1024 * 1024  # 500 MB
            if (total_size + new_file_size_bytes) > max_bytes:
                logger.warning(
                    f"User {user_id} upload rejected: aggregate storage size limit (500MB) exceeded."
                )
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking upload quota for user {user_id}: {e}")
            return True  # Fail open in case of DB queries crash

    async def verify_request_quota(self, user_id: UUID) -> bool:
        """Verify if the user is within their daily request quotas (1000 per day)."""
        if self._redis:
            try:
                user_str = str(user_id)
                key = f"quota:user:{user_str}:daily_requests"
                count_val = await self._redis.get(key)
                if count_val:
                    count = int(count_val)
                    if count >= 1000:
                        logger.warning(
                            f"User {user_id} request blocked: daily request limit (1000) reached."
                        )
                        return False
            except Exception as e:
                logger.error(f"Error checking request quota for user {user_id}: {e}")

        return True

    async def increment_request_count(self, user_id: UUID) -> None:
        """Increment daily request quota count for a user."""
        if self._redis:
            try:
                user_str = str(user_id)
                key = f"quota:user:{user_str}:daily_requests"
                async with self._redis.pipeline() as pipe:
                    pipe.incr(key)
                    # Keep key alive for 24 hours
                    pipe.expire(key, 86400)
                    await pipe.execute()
            except Exception as e:
                logger.error(
                    f"Error incrementing request count for user {user_id}: {e}"
                )
