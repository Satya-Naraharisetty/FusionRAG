import hashlib
import logging
import secrets
from datetime import timedelta
from uuid import UUID

from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    EmailNotVerifiedException,
    ExpiredVerificationTokenException,
    InvalidCredentialsException,
    InvalidSessionException,
    InvalidVerificationTokenException,
    MaxVerificationAttemptsException,
    UserNotFoundException,
)
from app.auth.domain.interfaces import (
    EmailVerificationRepository,
    PasswordHasher,
    SessionRepository,
    TimeProvider,
    TokenProvider,
    UnitOfWork,
    UserRepository,
    UUIDGenerator,
)
from app.auth.domain.schemas import (
    EmailVerificationTokenDomain,
    SessionDomain,
    UserDomain,
)
from app.core.config import settings
from app.core.email.resend_service import ResendEmailService

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
        verification_repo: EmailVerificationRepository | None = None,
        email_service: ResendEmailService | None = None,
    ) -> None:
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._hasher = hasher
        self._token_provider = token_provider
        self._time_provider = time_provider
        self._uuid_generator = uuid_generator
        self._uow = uow
        self._verification_repo = verification_repo
        self._email_service = email_service

    async def register_user(self, email: str, password: str) -> UserDomain:
        """
        Register a new user account with is_verified=False and dispatch a verification email.
        """
        try:
            normalized_email = email.strip().lower()
            now = self._time_provider.get_now()
            existing = await self._user_repo.get_by_email(normalized_email)
            if existing:
                cutoff = now - timedelta(days=settings.UNVERIFIED_USER_CLEANUP_DAYS)
                if not existing.is_verified and existing.created_at < cutoff:
                    logger.info(
                        "Purging stale unverified user account for %s created at %s",
                        normalized_email,
                        existing.created_at,
                    )
                    await self._user_repo.delete(existing.id)
                else:
                    # Return a duplicate account error to prevent registration conflicts
                    raise DuplicateAccountException("Email is already registered.")

            hashed_password = self._hasher.hash(password)
            user = UserDomain(
                id=self._uuid_generator.generate(),
                email=normalized_email,
                hashed_password=hashed_password,
                role="user",
                is_active=True,
                is_verified=False,
                created_at=now,
                updated_at=now,
            )
            saved_user = await self._user_repo.save(user)

            # Generate verification token & OTP and dispatch email
            if self._verification_repo:
                raw_token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
                otp_code = f"{secrets.randbelow(1000000):06d}"
                expires_at = now + timedelta(
                    minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES
                )

                token_domain = EmailVerificationTokenDomain(
                    id=self._uuid_generator.generate(),
                    user_id=saved_user.id,
                    token_hash=token_hash,
                    otp_code=otp_code,
                    attempts=0,
                    expires_at=expires_at,
                    is_used=False,
                    created_at=now,
                )
                await self._verification_repo.create(token_domain)

                if self._email_service:
                    verify_url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={raw_token}"
                    try:
                        await self._email_service.send_verification_email(
                            to_email=saved_user.email,
                            verify_url=verify_url,
                            otp_code=otp_code,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to dispatch verification email on register: %s", e
                        )

            await self._uow.commit()
            return saved_user
        except Exception:
            await self._uow.rollback()
            raise

    async def authenticate_user(self, email: str, password: str) -> UserDomain:
        """
        Authenticate user credentials during login.
        """
        normalized_email = email.strip().lower()
        user = await self._user_repo.get_by_email(normalized_email)
        if not user:
            raise InvalidCredentialsException("Invalid email or password.")

        if not user.is_active:
            raise AccountDisabledException("Account has been deactivated.")

        if settings.REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
            raise EmailNotVerifiedException(
                "Please verify your email address before logging in."
            )

        if not user.hashed_password:
            raise InvalidCredentialsException("Invalid email or password.")

        if not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentialsException("Invalid email or password.")

        return user

    async def verify_email(
        self,
        token: str | None = None,
        email: str | None = None,
        otp: str | None = None,
    ) -> UserDomain:
        """
        Verify a user's email via link token or 6-digit OTP code.
        """
        if not self._verification_repo:
            raise InvalidVerificationTokenException(
                "Email verification is not configured."
            )

        now = self._time_provider.get_now()
        try:
            if token:
                token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
                rec = await self._verification_repo.get_by_token_hash(token_hash)
                if not rec or rec.is_used:
                    raise InvalidVerificationTokenException(
                        "Invalid or already used verification link."
                    )
                if rec.expires_at < now:
                    raise ExpiredVerificationTokenException(
                        "Verification link has expired. Please request a new code."
                    )

                user = await self._user_repo.get_by_id(rec.user_id)
                if not user:
                    raise UserNotFoundException("User account not found.")

                await self._verification_repo.mark_used(rec.id)
                updated_user = UserDomain(
                    **{
                        **user.model_dump(),
                        "is_verified": True,
                        "updated_at": now,
                    }
                )
                saved_user = await self._user_repo.save(updated_user)
                await self._uow.commit()
                return saved_user

            elif email and otp:
                normalized_email = email.strip().lower()
                user = await self._user_repo.get_by_email(normalized_email)
                if not user:
                    raise InvalidVerificationTokenException("Account not found.")

                if user.is_verified:
                    return user

                rec = await self._verification_repo.get_latest_by_user_id(user.id)
                if not rec:
                    raise InvalidVerificationTokenException(
                        "No pending verification found. Please request a new code."
                    )
                if rec.expires_at < now:
                    raise ExpiredVerificationTokenException(
                        "Verification code has expired. Please request a new code."
                    )
                if rec.attempts >= 5:
                    await self._verification_repo.mark_used(rec.id)
                    await self._uow.commit()
                    raise MaxVerificationAttemptsException(
                        "Too many incorrect attempts. Please request a new verification code."
                    )

                if not secrets.compare_digest(rec.otp_code, otp.strip()):
                    attempts = await self._verification_repo.increment_attempts(rec.id)
                    await self._uow.commit()
                    remaining = max(0, 5 - attempts)
                    raise InvalidVerificationTokenException(
                        f"Invalid verification code. {remaining} attempt(s) remaining."
                    )

                await self._verification_repo.mark_used(rec.id)
                updated_user = UserDomain(
                    **{
                        **user.model_dump(),
                        "is_verified": True,
                        "updated_at": now,
                    }
                )
                saved_user = await self._user_repo.save(updated_user)
                await self._uow.commit()
                return saved_user

            else:
                raise InvalidVerificationTokenException(
                    "Either verification token or email and OTP code must be provided."
                )
        except Exception:
            await self._uow.rollback()
            raise

    async def resend_verification_email(self, email: str) -> None:
        """
        Invalidate older pending verification tokens and dispatch a fresh code & link.
        """
        if not self._verification_repo or not self._email_service:
            return

        try:
            normalized_email = email.strip().lower()
            user = await self._user_repo.get_by_email(normalized_email)
            if not user or user.is_verified:
                # Silently return to avoid account enumeration
                return

            now = self._time_provider.get_now()
            # Invalidate older pending tokens
            await self._verification_repo.invalidate_all_for_user(user.id)

            # Generate new token & OTP
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            otp_code = f"{secrets.randbelow(1000000):06d}"
            expires_at = now + timedelta(
                minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES
            )

            token_domain = EmailVerificationTokenDomain(
                id=self._uuid_generator.generate(),
                user_id=user.id,
                token_hash=token_hash,
                otp_code=otp_code,
                attempts=0,
                expires_at=expires_at,
                is_used=False,
                created_at=now,
            )
            await self._verification_repo.create(token_domain)

            verify_url = (
                f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={raw_token}"
            )
            await self._email_service.send_verification_email(
                to_email=user.email,
                verify_url=verify_url,
                otp_code=otp_code,
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def create_session(
        self,
        user_id: UUID,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a new active session, generating access and refresh tokens.
        """
        try:
            user = await self._user_repo.get_by_id(user_id)
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
            await self._session_repo.create(session, refresh_token)
            await self._uow.commit()

            return access_token, refresh_token
        except Exception:
            await self._uow.rollback()
            raise

    async def refresh_session(
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
            session = await self._session_repo.find_active_by_token(raw_refresh_token)

            if not session:
                # Token reuse / theft detection check:
                past_session = await self._session_repo.find_by_token(raw_refresh_token)
                if past_session:
                    user_id = past_session.user_id
                    # Revoke all active sessions for this user to protect the account
                    await self._session_repo.revoke_all_for_user(user_id)
                    await self._uow.commit()
                    logger.warning(
                        "Refresh token reuse detected",
                        extra={
                            "user_id": str(user_id),
                            "ip": ip_address,
                            "user_agent": user_agent,
                        },
                    )
                raise InvalidSessionException("Session expired or invalid.")

            # 2. Verify user is still active and valid
            user = await self._user_repo.get_by_id(session.user_id)
            if not user or not user.is_active:
                raise AccountDisabledException("Account is inactive.")

            # 3. Revoke existing session
            await self._session_repo.revoke(raw_refresh_token)

            # 4. Generate rotated tokens
            claims = {
                "sub": str(user.id),
                "role": user.role,
            }
            new_access_token = self._token_provider.create_access_token(claims)
            new_refresh_token = self._token_provider.create_refresh_token(claims)

            now = self._time_provider.get_now()
            expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            # 5. Persist rotated session
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
            await self._session_repo.create(new_session, new_refresh_token)

            # 6. Commit atomically
            await self._uow.commit()

            return new_access_token, new_refresh_token
        except (InvalidSessionException, AccountDisabledException):
            raise
        except Exception:
            await self._uow.rollback()
            raise

    async def revoke_session(self, raw_refresh_token: str) -> None:
        """
        Revoke an active refresh token session (logout).
        """
        try:
            await self._session_repo.revoke(raw_refresh_token)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def update_password(
        self,
        user_id: UUID,
        new_password: str,
        current_password: str | None = None,
    ) -> None:
        """
        Update or set a user's password.

        If the user already has a password set, current_password is required and verified.
        If the user is an OAuth-only user (no password set), current_password is not required.
        """
        try:
            user = await self._user_repo.get_by_id(user_id)
            if not user:
                raise UserNotFoundException("User account no longer exists.")

            if user.hashed_password:
                if not current_password:
                    raise InvalidCredentialsException("Current password is required.")
                if not self._hasher.verify(current_password, user.hashed_password):
                    raise InvalidCredentialsException("Current password is incorrect.")

            new_hash = self._hasher.hash(new_password)
            now = self._time_provider.get_now()
            updated = UserDomain(
                **{
                    **user.model_dump(),
                    "hashed_password": new_hash,
                    "updated_at": now,
                }
            )
            await self._user_repo.save(updated)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def verify_user_password(
        self, user_id: UUID, password: str | None = None
    ) -> None:
        """
        Re-verify a user's password before a destructive action (account deletion).
        If the account has no password set (OAuth-only), verification passes directly.
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundException("User account no longer exists.")
        if user.hashed_password:
            if not password:
                raise InvalidCredentialsException(
                    "Password is required to delete account."
                )
            if not self._hasher.verify(password, user.hashed_password):
                raise InvalidCredentialsException("Invalid email or password.")

    async def delete_user(self, user_id: UUID) -> None:
        """
        Permanently delete a user account.
        """
        try:
            user = await self._user_repo.get_by_id(user_id)
            if not user:
                raise UserNotFoundException("User account no longer exists.")
            await self._user_repo.delete(user_id)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def get_user_by_id(self, user_id: UUID) -> UserDomain | None:
        """
        Query a user by UUID.
        """
        return await self._user_repo.get_by_id(user_id)

    async def get_or_create_magic_link_user(self, email: str) -> UserDomain:
        """
        Find an existing user by email or create a new passwordless user account.
        """
        try:
            normalized_email = email.strip().lower()
            user = await self._user_repo.get_by_email(normalized_email)
            if user:
                if not user.is_verified:
                    now = self._time_provider.get_now()
                    updated = UserDomain(
                        **{**user.model_dump(), "is_verified": True, "updated_at": now}
                    )
                    user = await self._user_repo.save(updated)
                    await self._uow.commit()
                return user

            now = self._time_provider.get_now()
            new_user = UserDomain(
                id=self._uuid_generator.generate(),
                email=normalized_email,
                hashed_password=None,
                role="user",
                is_active=True,
                is_verified=True,
                created_at=now,
                updated_at=now,
                oauth_provider="magic_link",
            )
            saved = await self._user_repo.save(new_user)
            await self._uow.commit()
            return saved
        except Exception:
            await self._uow.rollback()
            raise

    async def cleanup_expired_unverified_users(
        self, days: int | None = None
    ) -> int:
        """
        Purge all unverified user accounts created older than `days` days ago.
        """
        cleanup_days = (
            days if days is not None else settings.UNVERIFIED_USER_CLEANUP_DAYS
        )
        try:
            now = self._time_provider.get_now()
            cutoff = now - timedelta(days=cleanup_days)
            count = await self._user_repo.delete_unverified_older_than(cutoff)
            await self._uow.commit()
            if count > 0:
                logger.info(
                    "Cleaned up %d expired unverified user account(s) older than %d days",
                    count,
                    cleanup_days,
                )
            return count
        except Exception:
            await self._uow.rollback()
            raise

