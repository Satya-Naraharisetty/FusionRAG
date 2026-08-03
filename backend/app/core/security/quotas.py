import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.documents.infrastructure.persistence.models import SQLAlchemyDocument

logger = logging.getLogger(__name__)


class ResourceQuotaService:
    def __init__(self, db: Session, redis_client: Optional[Any] = None) -> None:
        self.db = db
        self._redis = redis_client

    async def verify_upload_quota(self, user_id: UUID, new_file_size_bytes: int) -> bool:
        """
        Verify if the user is within their document upload quotas.
        Checks total uploaded document count and aggregate storage size limits.
        """
        try:
            # 1. Enforce max document count (e.g., 50 documents limit)
            doc_count = (
                self.db.query(SQLAlchemyDocument)
                .filter(SQLAlchemyDocument.user_id == user_id)
                .count()
            )
            if doc_count >= 50:
                logger.warning(f"User {user_id} upload rejected: document limit (50) reached.")
                return False

            # 2. Enforce max storage size limit (e.g., 500 MB limit)
            total_size = (
                self.db.query(func.sum(SQLAlchemyDocument.file_size))
                .filter(SQLAlchemyDocument.user_id == user_id)
                .scalar()
                or 0
            )
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
                count_str = self._redis.get(key)
                if count_str:
                    count = int(count_str)
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
                pipe = self._redis.pipeline()
                pipe.incr(key)
                # Keep key alive for 24 hours
                pipe.expire(key, 86400)
                pipe.execute()
            except Exception as e:
                logger.error(f"Error incrementing request count for user {user_id}: {e}")
