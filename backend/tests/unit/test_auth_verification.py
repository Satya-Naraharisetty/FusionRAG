import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.auth.domain.exceptions import (
    EmailNotVerifiedException,
    ExpiredVerificationTokenException,
    InvalidVerificationTokenException,
    MaxVerificationAttemptsException,
)
from app.auth.domain.schemas import (
    EmailVerificationTokenDomain,
    UserDomain,
)
from app.auth.services.auth_service import AuthService
from app.core.config import settings


@pytest.fixture
def mock_deps(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
    user_repo = AsyncMock()
    session_repo = AsyncMock()
    hasher = MagicMock()
    hasher.hash.return_value = "hashed_pw_123"
    hasher.verify.return_value = True
    token_provider = MagicMock()
    token_provider.create_access_token.return_value = "access_token_xyz"
    token_provider.create_refresh_token.return_value = "refresh_token_abc"
    time_provider = MagicMock()
    now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)
    time_provider.get_now.return_value = now
    uuid_generator = MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()
    uow = AsyncMock()
    verification_repo = AsyncMock()
    email_service = AsyncMock()
    email_service.send_verification_email.return_value = True

    service = AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        hasher=hasher,
        token_provider=token_provider,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        uow=uow,
        verification_repo=verification_repo,
        email_service=email_service,
    )
    return {
        "service": service,
        "user_repo": user_repo,
        "session_repo": session_repo,
        "hasher": hasher,
        "time_provider": time_provider,
        "uuid_generator": uuid_generator,
        "uow": uow,
        "verification_repo": verification_repo,
        "email_service": email_service,
        "now": now,
    }


@pytest.mark.asyncio
async def test_register_user_creates_unverified_user_and_dispatches_email(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    email_service = mock_deps["email_service"]

    user_repo.get_by_email.return_value = None
    user_repo.save.side_effect = lambda u: u

    user = await service.register_user("newuser@example.com", "Password123!")

    assert user.email == "newuser@example.com"
    assert user.is_verified is False
    verification_repo.create.assert_called_once()
    created_token = verification_repo.create.call_args[0][0]
    assert len(created_token.otp_code) == 6
    assert created_token.is_used is False
    email_service.send_verification_email.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_unverified_user_raises_exception(mock_deps, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]

    unverified_user = UserDomain(
        id=uuid4(),
        email="unverified@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=mock_deps["now"],
        updated_at=mock_deps["now"],
    )
    user_repo.get_by_email.return_value = unverified_user

    with pytest.raises(EmailNotVerifiedException):
        await service.authenticate_user("unverified@example.com", "Password123!")


@pytest.mark.asyncio
async def test_verify_email_via_token_success(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    now = mock_deps["now"]

    raw_token = "valid_raw_token_string"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    user_id = uuid4()

    token_record = EmailVerificationTokenDomain(
        id=uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        otp_code="123456",
        attempts=0,
        expires_at=now + timedelta(minutes=15),
        is_used=False,
        created_at=now,
    )
    verification_repo.get_by_token_hash.return_value = token_record

    existing_user = UserDomain(
        id=user_id,
        email="verify@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_id.return_value = existing_user
    user_repo.save.side_effect = lambda u: u

    verified_user = await service.verify_email(token=raw_token)

    assert verified_user.is_verified is True
    verification_repo.mark_used.assert_called_once_with(token_record.id)


@pytest.mark.asyncio
async def test_verify_email_via_otp_success(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    now = mock_deps["now"]

    user_id = uuid4()
    existing_user = UserDomain(
        id=user_id,
        email="otp@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_email.return_value = existing_user
    user_repo.save.side_effect = lambda u: u

    token_record = EmailVerificationTokenDomain(
        id=uuid4(),
        user_id=user_id,
        token_hash="some_hash",
        otp_code="654321",
        attempts=1,
        expires_at=now + timedelta(minutes=15),
        is_used=False,
        created_at=now,
    )
    verification_repo.get_latest_by_user_id.return_value = token_record

    verified_user = await service.verify_email(email="otp@example.com", otp="654321")

    assert verified_user.is_verified is True
    verification_repo.mark_used.assert_called_once_with(token_record.id)


@pytest.mark.asyncio
async def test_verify_email_wrong_otp_increments_attempts(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    now = mock_deps["now"]

    user_id = uuid4()
    existing_user = UserDomain(
        id=user_id,
        email="wrongotp@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_email.return_value = existing_user

    token_record = EmailVerificationTokenDomain(
        id=uuid4(),
        user_id=user_id,
        token_hash="some_hash",
        otp_code="654321",
        attempts=2,
        expires_at=now + timedelta(minutes=15),
        is_used=False,
        created_at=now,
    )
    verification_repo.get_latest_by_user_id.return_value = token_record
    verification_repo.increment_attempts.return_value = 3

    with pytest.raises(InvalidVerificationTokenException) as exc_info:
        await service.verify_email(email="wrongotp@example.com", otp="000000")

    assert "2 attempt(s) remaining" in str(exc_info.value)
    verification_repo.increment_attempts.assert_called_once_with(token_record.id)


@pytest.mark.asyncio
async def test_verify_email_max_attempts_locks_token(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    now = mock_deps["now"]

    user_id = uuid4()
    existing_user = UserDomain(
        id=user_id,
        email="locked@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_email.return_value = existing_user

    token_record = EmailVerificationTokenDomain(
        id=uuid4(),
        user_id=user_id,
        token_hash="some_hash",
        otp_code="654321",
        attempts=5,
        expires_at=now + timedelta(minutes=15),
        is_used=False,
        created_at=now,
    )
    verification_repo.get_latest_by_user_id.return_value = token_record

    with pytest.raises(MaxVerificationAttemptsException):
        await service.verify_email(email="locked@example.com", otp="654321")

    verification_repo.mark_used.assert_called_once_with(token_record.id)


@pytest.mark.asyncio
async def test_verify_email_expired_raises_exception(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    now = mock_deps["now"]

    user_id = uuid4()
    existing_user = UserDomain(
        id=user_id,
        email="expired@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_email.return_value = existing_user

    token_record = EmailVerificationTokenDomain(
        id=uuid4(),
        user_id=user_id,
        token_hash="some_hash",
        otp_code="654321",
        attempts=0,
        expires_at=now - timedelta(minutes=1),  # Expired
        is_used=False,
        created_at=now - timedelta(minutes=16),
    )
    verification_repo.get_latest_by_user_id.return_value = token_record

    with pytest.raises(ExpiredVerificationTokenException):
        await service.verify_email(email="expired@example.com", otp="654321")


@pytest.mark.asyncio
async def test_resend_verification_email(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    verification_repo = mock_deps["verification_repo"]
    email_service = mock_deps["email_service"]
    now = mock_deps["now"]

    user_id = uuid4()
    existing_user = UserDomain(
        id=user_id,
        email="resend@example.com",
        hashed_password="hashed_pw_123",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    user_repo.get_by_email.return_value = existing_user

    await service.resend_verification_email("resend@example.com")

    verification_repo.invalidate_all_for_user.assert_called_once_with(user_id)
    verification_repo.create.assert_called_once()
    email_service.send_verification_email.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired_unverified_users(mock_deps):
    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    uow = mock_deps["uow"]
    now = mock_deps["now"]

    user_repo.delete_unverified_older_than.return_value = 3

    deleted_count = await service.cleanup_expired_unverified_users(days=7)

    expected_cutoff = now - timedelta(days=7)
    user_repo.delete_unverified_older_than.assert_called_once_with(expected_cutoff)
    uow.commit.assert_called_once()
    assert deleted_count == 3


@pytest.mark.asyncio
async def test_register_stale_unverified_user_purges_and_proceeds(mock_deps):

    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    now = mock_deps["now"]

    # User created 10 days ago and never verified
    stale_user = UserDomain(
        id=uuid4(),
        email="stale@example.com",
        hashed_password="hashed_pw_old",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=10),
    )
    user_repo.get_by_email.return_value = stale_user
    user_repo.save.side_effect = lambda u: u

    result = await service.register_user("stale@example.com", "NewPassword123!")

    user_repo.delete.assert_called_once_with(stale_user.id)
    assert result.email == "stale@example.com"
    assert result.is_verified is False


@pytest.mark.asyncio
async def test_register_recent_unverified_user_raises_duplicate(mock_deps):
    from app.auth.domain.exceptions import DuplicateAccountException

    service = mock_deps["service"]
    user_repo = mock_deps["user_repo"]
    now = mock_deps["now"]

    # User created 2 days ago and unverified
    recent_user = UserDomain(
        id=uuid4(),
        email="recent@example.com",
        hashed_password="hashed_pw_old",
        role="user",
        is_active=True,
        is_verified=False,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    user_repo.get_by_email.return_value = recent_user

    with pytest.raises(DuplicateAccountException):
        await service.register_user("recent@example.com", "NewPassword123!")

    user_repo.delete.assert_not_called()
