import logging
from datetime import timedelta
from uuid import UUID

from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    InvalidCredentialsException,
    InvalidSessionException,
    UserNotFoundException,
)
from app.auth.domain.interfaces import (
    PasswordHasher,
    SessionRepository,
    TimeProvider,
    TokenProvider,
    UnitOfWork,
    UserRepository,
    UUIDGenerator,
)
from app.auth.domain.schemas import SessionDomain, UserDomain
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        hasher: PasswordHasher,
        token_provider: TokenProvider,
        time_provider: TimeProvider,
        uuid_generator: UUIDGenerator,
        uow: UnitOfWork,
    ) -> None:
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._hasher = hasher
        self._token_provider = token_provider
        self._time_provider = time_provider
        self._uuid_generator = uuid_generator
        self._uow = uow

    def register_user(self, email: str, password: str) -> UserDomain:
        """
        Register a new user account after validating credentials and unique email check.
        """
        try:
            normalized_email = email.strip().lower()
            existing = self._user_repo.get_by_email(normalized_email)
            if existing:
                # Return a duplicate account error to prevent registration conflicts
                raise DuplicateAccountException("Email is already registered.")

            hashed_password = self._hasher.hash(password)
            user = UserDomain(
                id=self._uuid_generator.generate(),
                email=normalized_email,
                hashed_password=hashed_password,
                role="user",
                is_active=True,
                created_at=self._time_provider.get_now(),
                updated_at=self._time_provider.get_now(),
            )
            saved_user = self._user_repo.save(user)
            self._uow.commit()
            return saved_user
        except Exception:
            self._uow.rollback()
            raise

    def authenticate_user(self, email: str, password: str) -> UserDomain:
        """
        Authenticate user credentials during login.
        """
        normalized_email = email.strip().lower()
        user = self._user_repo.get_by_email(normalized_email)
        if not user:
            raise InvalidCredentialsException("Invalid email or password.")

        if not user.is_active:
            raise AccountDisabledException("Account has been deactivated.")

        if not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentialsException("Invalid email or password.")

        return user

    def create_session(
        self,
        user_id: UUID,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a new active session, generating access and refresh tokens.
        """
        try:
            user = self._user_repo.get_by_id(user_id)
            if not user:
                raise InvalidCredentialsException("User not found.")

            claims = {
                "sub": str(user_id),
                "role": user.role,
            }
            access_token = self._token_provider.create_access_token(claims)
            refresh_token = self._token_provider.create_refresh_token(claims)

            now = self._time_provider.get_now()
            expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            session = SessionDomain(
                id=self._uuid_generator.generate(),
                token_hash="",  # Set internally by repo
                user_id=user_id,
                expires_at=expires_at,
                is_revoked=False,
                created_at=now,
                last_used_at=now,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            self._session_repo.create(session, refresh_token)
            self._uow.commit()

            return access_token, refresh_token
        except Exception:
            self._uow.rollback()
            raise

    def refresh_session(
        self,
        raw_refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """
        Validate and rotate the refresh token session atomically in a single transaction.
        """
        try:
            # 1. Locate active session (locks the row via with_for_update)
            session = self._session_repo.find_active_by_token(raw_refresh_token)

            if not session:
                # Token reuse / theft detection check:
                past_session = self._session_repo.find_by_token(raw_refresh_token)
                if past_session:
                    user_id = past_session.user_id
                    # Revoke all active sessions for this user to protect the account
                    self._session_repo.revoke_all_for_user(user_id)
                    logger.warning(
                        "Refresh token reuse detected",
                        extra={
                            "user_id": str(user_id),
                            "event": "refresh_token_reuse",
                        },
                    )
                    self._uow.commit()  # Commit the mass revocation immediately
                raise InvalidSessionException(
                    "Session is invalid, expired, or revoked."
                )

            user = self._user_repo.get_by_id(session.user_id)
            if not user or not user.is_active:
                self._session_repo.revoke(raw_refresh_token)
                self._uow.commit()
                if not user:
                    raise InvalidSessionException(
                        "User associated with session no longer exists."
                    )
                else:
                    raise AccountDisabledException("Account has been deactivated.")

            # 3. Update last_used_at (IMPROVEMENT 5)
            now = self._time_provider.get_now()
            self._session_repo.update_last_used(raw_refresh_token, now)

            # 4. Revoke old session
            self._session_repo.revoke(raw_refresh_token)

            # 5. Create new session
            claims = {
                "sub": str(user.id),
                "role": user.role,
            }
            new_access_token = self._token_provider.create_access_token(claims)
            new_refresh_token = self._token_provider.create_refresh_token(claims)

            expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            new_session = SessionDomain(
                id=self._uuid_generator.generate(),
                token_hash="",
                user_id=user.id,
                expires_at=expires_at,
                is_revoked=False,
                created_at=now,
                last_used_at=now,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            self._session_repo.create(new_session, new_refresh_token)

            # 6. Commit atomically
            self._uow.commit()

            return new_access_token, new_refresh_token
        except Exception:
            self._uow.rollback()
            raise

    def revoke_session(self, raw_refresh_token: str) -> None:
        """
        Revoke an active refresh token session (logout).
        """
        try:
            self._session_repo.revoke(raw_refresh_token)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

    def verify_user_password(self, user_id: UUID, password: str) -> None:
        """
        Re-verify a user's password before a destructive action (account deletion).

        Unlike authenticate_user, this intentionally does not check is_active:
        a deactivated account may still be deleted by its owner when the
        correct password is supplied.

        Raises UserNotFoundException if the account no longer exists and
        InvalidCredentialsException if the password does not match, so the API
        layer responds with the standard error codes.
        """
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundException("User account no longer exists.")
        if not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentialsException("Invalid email or password.")

    def delete_user(self, user_id: UUID) -> None:
        """
        Permanently delete a user account.

        The database ON DELETE CASCADE constraints remove the user's refresh
        sessions (and any conversations, documents, etc.). Raises
        UserNotFoundException if the account no longer exists.
        """
        try:
            user = self._user_repo.get_by_id(user_id)
            if not user:
                raise UserNotFoundException("User account no longer exists.")
            self._user_repo.delete(user_id)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

    def get_user_by_id(self, user_id: UUID) -> UserDomain | None:
        """
        Query a user by UUID.
        """
        return self._user_repo.get_by_id(user_id)
