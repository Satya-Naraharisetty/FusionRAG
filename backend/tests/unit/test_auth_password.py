from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.auth.domain.exceptions import InvalidCredentialsException, UserNotFoundException
from app.auth.domain.schemas import (
    UpdatePasswordSchema,
    UserDomain,
    UserResponseSchema,
)
from app.auth.services.auth_service import AuthService


@pytest.fixture
def mock_auth_deps():
    user_repo = AsyncMock()
    session_repo = AsyncMock()
    hasher = MagicMock()
    hasher.hash.side_effect = lambda pw: f"hashed_{pw}"
    hasher.verify.side_effect = lambda pw, h: h == f"hashed_{pw}"
    token_provider = MagicMock()
    time_provider = MagicMock()
    now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)
    time_provider.get_now.return_value = now
    uuid_generator = MagicMock()
    uuid_generator.generate.side_effect = lambda: uuid4()
    uow = AsyncMock()

    service = AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        hasher=hasher,
        token_provider=token_provider,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        uow=uow,
    )
    return {
        "service": service,
        "user_repo": user_repo,
        "hasher": hasher,
        "time_provider": time_provider,
        "uow": uow,
    }


def test_user_domain_and_response_schema_has_password():
    oauth_user = UserDomain(
        id=uuid4(),
        email="oauth@example.com",
        hashed_password=None,
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        oauth_provider="google",
    )
    assert oauth_user.has_password is False

    response_schema = UserResponseSchema.model_validate(oauth_user)
    assert response_schema.has_password is False

    local_user = UserDomain(
        id=uuid4(),
        email="local@example.com",
        hashed_password="hashed_mypassword",
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert local_user.has_password is True

    response_schema_local = UserResponseSchema.model_validate(local_user)
    assert response_schema_local.has_password is True


def test_update_password_schema_validation():
    # Common banned password should fail validation
    with pytest.raises(ValueError, match="too common"):
        UpdatePasswordSchema(new_password="password123")

    # Valid password should succeed
    schema = UpdatePasswordSchema(new_password="SecurePassword2026!")
    assert schema.new_password == "SecurePassword2026!"


@pytest.mark.asyncio
async def test_update_password_for_oauth_user_without_current_password(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]
    uow = mock_auth_deps["uow"]

    user_id = uuid4()
    oauth_user = UserDomain(
        id=user_id,
        email="oauth@example.com",
        hashed_password=None,
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        oauth_provider="google",
    )
    user_repo.get_by_id.return_value = oauth_user
    user_repo.save.side_effect = lambda u: u

    await service.update_password(user_id=user_id, new_password="NewSecurePassword123!")

    user_repo.save.assert_called_once()
    saved_user = user_repo.save.call_args[0][0]
    assert saved_user.hashed_password == "hashed_NewSecurePassword123!"
    uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_for_existing_password_user_success(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]
    uow = mock_auth_deps["uow"]

    user_id = uuid4()
    local_user = UserDomain(
        id=user_id,
        email="local@example.com",
        hashed_password="hashed_OldPassword123!",
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    user_repo.get_by_id.return_value = local_user
    user_repo.save.side_effect = lambda u: u

    await service.update_password(
        user_id=user_id,
        new_password="NewSecurePassword123!",
        current_password="OldPassword123!",
    )

    user_repo.save.assert_called_once()
    saved_user = user_repo.save.call_args[0][0]
    assert saved_user.hashed_password == "hashed_NewSecurePassword123!"
    uow.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_password_requires_current_password_if_set(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]

    user_id = uuid4()
    local_user = UserDomain(
        id=user_id,
        email="local@example.com",
        hashed_password="hashed_OldPassword123!",
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    user_repo.get_by_id.return_value = local_user

    with pytest.raises(InvalidCredentialsException, match="Current password is required"):
        await service.update_password(
            user_id=user_id,
            new_password="NewSecurePassword123!",
            current_password=None,
        )


@pytest.mark.asyncio
async def test_update_password_wrong_current_password_fails(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]

    user_id = uuid4()
    local_user = UserDomain(
        id=user_id,
        email="local@example.com",
        hashed_password="hashed_OldPassword123!",
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    user_repo.get_by_id.return_value = local_user

    with pytest.raises(InvalidCredentialsException, match="Current password is incorrect"):
        await service.update_password(
            user_id=user_id,
            new_password="NewSecurePassword123!",
            current_password="WrongPassword123!",
        )


@pytest.mark.asyncio
async def test_verify_user_password_allows_oauth_user_without_password(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]

    user_id = uuid4()
    oauth_user = UserDomain(
        id=user_id,
        email="oauth@example.com",
        hashed_password=None,
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        oauth_provider="google",
    )
    user_repo.get_by_id.return_value = oauth_user

    # Should not raise exception
    await service.verify_user_password(user_id=user_id, password=None)


@pytest.mark.asyncio
async def test_verify_user_password_requires_password_if_user_has_one(mock_auth_deps):
    service = mock_auth_deps["service"]
    user_repo = mock_auth_deps["user_repo"]

    user_id = uuid4()
    local_user = UserDomain(
        id=user_id,
        email="local@example.com",
        hashed_password="hashed_MyPassword123!",
        role="user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    user_repo.get_by_id.return_value = local_user

    with pytest.raises(InvalidCredentialsException, match="Password is required"):
        await service.verify_user_password(user_id=user_id, password=None)

    with pytest.raises(InvalidCredentialsException, match="Invalid email or password"):
        await service.verify_user_password(user_id=user_id, password="WrongPassword123!")

    # Correct password succeeds
    await service.verify_user_password(user_id=user_id, password="MyPassword123!")
