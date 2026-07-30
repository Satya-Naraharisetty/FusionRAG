import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth.domain.interfaces import TimeProvider, UnitOfWork, UUIDGenerator


class SystemTimeProvider(TimeProvider):
    def get_now(self) -> datetime:
        """
        Return the current timezone-aware UTC datetime.
        """
        return datetime.now(UTC)


class SystemUUIDGenerator(UUIDGenerator):
    def generate(self) -> uuid.UUID:
        """
        Generate a random UUID v4.
        """
        return uuid.uuid4()


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, db: Session) -> None:
        self._db = db

    def commit(self) -> None:
        """
        Commit the active transaction.
        """
        self._db.commit()

    def rollback(self) -> None:
        """
        Rollback the active transaction.
        """
        self._db.rollback()
