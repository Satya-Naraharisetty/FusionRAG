from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.domain.interfaces import UserRepository
from app.auth.domain.schemas import UserDomain
from app.auth.infrastructure.persistence.models import SQLAlchemyUser


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_email(self, email: str) -> UserDomain | None:
        """
        Query a user by normalized email address.
        """
        db_user = (
            self._db.query(SQLAlchemyUser).filter(SQLAlchemyUser.email == email).first()
        )
        if not db_user:
            return None
        return UserDomain.model_validate(db_user)

    def get_by_id(self, id: UUID) -> UserDomain | None:
        """
        Query a user by UUID.
        """
        db_user = self._db.query(SQLAlchemyUser).filter(SQLAlchemyUser.id == id).first()
        if not db_user:
            return None
        return UserDomain.model_validate(db_user)

    def save(self, user: UserDomain) -> UserDomain:
        """
        Save/persist a user model in the database transaction context.
        """
        db_user = (
            self._db.query(SQLAlchemyUser).filter(SQLAlchemyUser.id == user.id).first()
        )
        if not db_user:
            db_user = SQLAlchemyUser(
                id=user.id,
                email=user.email,
                hashed_password=user.hashed_password,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
            self._db.add(db_user)
        else:
            db_user.email = user.email
            db_user.hashed_password = user.hashed_password
            db_user.role = user.role
            db_user.is_active = user.is_active
            db_user.updated_at = user.updated_at

        self._db.flush()
        return UserDomain.model_validate(db_user)
