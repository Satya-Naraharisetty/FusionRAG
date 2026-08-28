import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.dependencies import (
    get_account_delete_rate_limiter,
    get_login_failed_attempts_tracker,
)
from app.core.config import settings
from app.core.security.rate_limiter import LoginAttemptTracker, RateLimiter
from app.db.models import Base
from tests.db import TEST_DATABASE_URL


def _truncate_auth_tables(session) -> None:
    """Delete every user and session so tests start from (and end on) a clean slate."""
    session.execute(text("DELETE FROM email_verification_tokens;"))
    session.execute(text("DELETE FROM refresh_sessions;"))
    session.execute(text("DELETE FROM users;"))
    session.commit()


@pytest.fixture(scope="function")
def test_db(client):
    """
    Fixture to set up a clean Postgres test database connection,
    truncating users and sessions before each test runs.
    """
    sync_engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async_url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(async_url, poolclass=NullPool)
    try:
        Base.metadata.create_all(bind=sync_engine)

        sync_session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=sync_engine
        )

        # Clean the tables to guarantee test isolation
        db = sync_session_local()
        try:
            _truncate_auth_tables(db)
        finally:
            db.close()

        async_session_local = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # Wire our test database session factory into the application state
        client.app.state.db_session_factory = async_session_local

        yield async_session_local

        # Teardown: truncate again as hygiene so no test (not even the last one in
        # the file) leaves users/sessions behind.
        db = sync_session_local()
        try:
            _truncate_auth_tables(db)
        finally:
            db.close()
    finally:
        sync_engine.dispose()


def test_register_user_success(client, test_db):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "SecurePassword123!"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert data["role"] == "user"
    assert data["is_active"] is True


def test_register_duplicate_email_fails(client, test_db):
    # First registration
    client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "password": "SecurePassword123!"},
    )

    # Second registration with same email
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "password": "AnotherPassword123!"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error"]["code"] == "DUPLICATE_ACCOUNT"


def test_register_weak_password_fails(client, test_db):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "password"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_login_success_sets_cookies(client, test_db):
    # Create user
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "SecurePassword123!"},
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "SecurePassword123!"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "expires_in" in data

    # Verify cookie was set
    assert settings.COOKIE_NAME in response.cookies


def test_login_invalid_password_fails(client, test_db):
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrong@example.com", "password": "SecurePassword123!"},
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_get_me_profile_success(client, test_db):
    # Create and login
    client.post(
        "/api/v1/auth/register",
        json={"email": "profile@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "profile@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]

    # Access /me
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "profile@example.com"


def test_get_me_unauthorized_fails(client, test_db):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token_rotation_success(client, test_db):
    client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "SecurePassword123!"},
    )
    cookie_before = login_res.cookies[settings.COOKIE_NAME]

    # Refresh token rotation call
    client.cookies.set(settings.COOKIE_NAME, cookie_before)
    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data

    # Verify cookie has been updated/rotated
    cookie_after = response.cookies[settings.COOKIE_NAME]
    assert cookie_before != cookie_after


def test_logout_invalidates_session(client, test_db):
    client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "SecurePassword123!"},
    )
    cookie = login_res.cookies[settings.COOKIE_NAME]

    # Logout
    client.cookies.set(settings.COOKIE_NAME, cookie)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == status.HTTP_200_OK

    # Attempt to refresh with the logged-out cookie
    client.cookies.set(settings.COOKIE_NAME, cookie)
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token_reuse_detection_mitigates_threat(client, test_db):
    client.post(
        "/api/v1/auth/register",
        json={"email": "attacker@example.com", "password": "SecurePassword123!"},
    )
    # Log in to get active session
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "attacker@example.com", "password": "SecurePassword123!"},
    )
    cookie_v1 = login_res.cookies[settings.COOKIE_NAME]

    # Also log in a second time to simulate a concurrent active session
    login_res_2 = client.post(
        "/api/v1/auth/login",
        json={"email": "attacker@example.com", "password": "SecurePassword123!"},
    )
    cookie_other = login_res_2.cookies[settings.COOKIE_NAME]

    # Rotate cookie_v1 once to get cookie_v2. This revokes cookie_v1.
    client.cookies.set(settings.COOKIE_NAME, cookie_v1)
    rotate_res = client.post("/api/v1/auth/refresh")
    assert rotate_res.status_code == status.HTTP_200_OK
    cookie_v2 = rotate_res.cookies[settings.COOKIE_NAME]

    # NOW, simulate the threat: Re-submit the revoked cookie_v1!
    client.cookies.set(settings.COOKIE_NAME, cookie_v1)
    threat_res = client.post("/api/v1/auth/refresh")
    assert threat_res.status_code == status.HTTP_401_UNAUTHORIZED
    assert threat_res.json()["error"]["code"] == "INVALID_SESSION"

    # Threat mitigation verify:
    # 1. The valid rotated session (cookie_v2) must be revoked/blocked.
    client.cookies.set(settings.COOKIE_NAME, cookie_v2)
    verify_v2 = client.post("/api/v1/auth/refresh")
    assert verify_v2.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. The second concurrent active session (cookie_other) must also be revoked!
    client.cookies.set(settings.COOKIE_NAME, cookie_other)
    verify_other = client.post("/api/v1/auth/refresh")
    assert verify_other.status_code == status.HTTP_401_UNAUTHORIZED


def test_delete_account_success_cascades(client, test_db):
    """
    DELETE /auth/account removes the user and cascades refresh sessions.
    """
    register_res = client.post(
        "/api/v1/auth/register",
        json={"email": "delete@example.com", "password": "SecurePassword123!"},
    )
    user_id = register_res.json()["id"]
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "delete@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]
    cookie = login_res.cookies[settings.COOKIE_NAME]

    # Delete the account (password re-entry is required)
    response = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "SecurePassword123!"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # The refresh cookie must be cleared so the browser drops the stale session
    assert "refresh_token=" in response.headers.get("set-cookie", "")

    # The user row and its sessions must be gone (DB-level cascade)
    sync_engine = create_engine(TEST_DATABASE_URL)
    try:
        with sync_engine.connect() as conn:
            user_count = conn.execute(
                text("SELECT count(*) FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).scalar()
            session_count = conn.execute(
                text("SELECT count(*) FROM refresh_sessions WHERE user_id = :uid"),
                {"uid": user_id},
            ).scalar()
    finally:
        sync_engine.dispose()
    assert user_count == 0
    assert session_count == 0

    # Login with the same credentials now fails
    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": "delete@example.com", "password": "SecurePassword123!"},
    )
    assert relogin.status_code == status.HTTP_401_UNAUTHORIZED
    assert relogin.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # Refresh with the old cookie fails (session was cascaded away)
    client.cookies.set(settings.COOKIE_NAME, cookie)
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    # /me with the old access token reports the account no longer exists
    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_account_unauthorized_fails(client, test_db):
    response = client.request("DELETE", "/api/v1/auth/account", json={"password": "x"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_delete_account_wrong_password_fails(client, test_db):
    """
    DELETE /auth/account with the wrong password is rejected (401) and the
    account survives — a stolen access token alone cannot delete the account.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "reenter@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "reenter@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]

    # Wrong password -> 401 INVALID_CREDENTIALS
    denied = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "WrongPassword!"},
    )
    assert denied.status_code == status.HTTP_401_UNAUTHORIZED
    assert denied.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # Account still exists: login with the correct password still succeeds
    relogin = client.post(
        "/api/v1/auth/login",
        json={"email": "reenter@example.com", "password": "SecurePassword123!"},
    )
    assert relogin.status_code == status.HTTP_200_OK

    # Correct password then succeeds
    granted = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "SecurePassword123!"},
    )
    assert granted.status_code == status.HTTP_204_NO_CONTENT


def test_delete_account_rate_limited(client, test_db):
    """
    DELETE /auth/account is rate-limited per user so the password re-entry
    field cannot be brute-forced with a compromised access token.

    The real limiter is Redis-backed; here we inject a persistent in-memory
    limiter (2 per minute) so the 429 behavior is deterministic regardless of
    whether Redis is reachable from the test runner.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "ratelimit@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ratelimit@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]

    shared_limiter = RateLimiter(redis_client=None, requests_per_minute=2, burst=0)
    client.app.dependency_overrides[get_account_delete_rate_limiter] = lambda: (
        shared_limiter
    )
    try:
        statuses = []
        for _ in range(3):
            res = client.request(
                "DELETE",
                "/api/v1/auth/account",
                headers={"Authorization": f"Bearer {token}"},
                json={"password": "WrongPassword!"},
            )
            statuses.append(res.status_code)

        # First two attempts are checked (401 wrong password); the third is
        # blocked by the rate limiter before the handler runs.
        assert statuses[:2] == [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_401_UNAUTHORIZED,
        ]
        assert statuses[2] == status.HTTP_429_TOO_MANY_REQUESTS
    finally:
        client.app.dependency_overrides.pop(get_account_delete_rate_limiter, None)


def test_delete_account_missing_user_returns_not_found(client, test_db):
    """
    Deleting an already-deleted account returns 404 with a USER_NOT_FOUND code.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "twice@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "twice@example.com", "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]

    first = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "SecurePassword123!"},
    )
    assert first.status_code == status.HTTP_204_NO_CONTENT

    second = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "SecurePassword123!"},
    )
    assert second.status_code == status.HTTP_404_NOT_FOUND
    assert second.json()["error"]["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_refresh_concurrency_fails(client, test_db):
    """
    Test two simultaneous refresh requests using the same refresh token.
    Exactly one request must succeed, and the other must trigger reuse/revocation and fail.
    """
    import asyncio

    import httpx
    from httpx import ASGITransport

    async with httpx.AsyncClient(
        transport=ASGITransport(app=client.app), base_url="http://test"
    ) as async_client:
        await async_client.post(
            "/api/v1/auth/register",
            json={"email": "concurrent@example.com", "password": "SecurePassword123!"},
        )
        login_res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "concurrent@example.com", "password": "SecurePassword123!"},
        )
        cookie_v1 = login_res.cookies.get(settings.COOKIE_NAME)

        client1 = httpx.AsyncClient(
            transport=ASGITransport(app=client.app),
            base_url="http://test",
            cookies={settings.COOKIE_NAME: cookie_v1},
        )
        client2 = httpx.AsyncClient(
            transport=ASGITransport(app=client.app),
            base_url="http://test",
            cookies={settings.COOKIE_NAME: cookie_v1},
        )
        try:
            results = await asyncio.gather(
                client1.post("/api/v1/auth/refresh"),
                client2.post("/api/v1/auth/refresh"),
                return_exceptions=True,
            )
        finally:
            await client1.aclose()
            await client2.aclose()

    # Exactly one request must succeed (200 OK), and one must fail (401)
    status_codes = [r.status_code for r in results if not isinstance(r, Exception)]
    assert 200 in status_codes
    assert 401 in status_codes


def test_login_rate_limiting_lockout(client, test_db):
    """
    Test that entering wrong credentials more than 5 times locks the user/IP
    out with HTTP 429 and a 5-minute lockout window.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "lockout@example.com", "password": "SecurePassword123!"},
    )

    shared_limiter = LoginAttemptTracker(
        redis_client=None,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=float(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    )
    client.app.dependency_overrides[get_login_failed_attempts_tracker] = lambda: (
        shared_limiter
    )

    try:
        # 5 attempts with wrong password
        statuses = []
        for _ in range(5):
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "lockout@example.com", "password": "WrongPassword1!"},
            )
            statuses.append(res.status_code)

        # First 5 attempts return 401 Unauthorized
        assert statuses == [status.HTTP_401_UNAUTHORIZED] * 5

        # 6th attempt (exceeding 5 attempts) is blocked with HTTP 429 Too Many Requests
        blocked_res = client.post(
            "/api/v1/auth/login",
            json={"email": "lockout@example.com", "password": "WrongPassword1!"},
        )
        assert blocked_res.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        body = blocked_res.json()
        error_msg = body.get("detail") or body.get("error", {}).get("message", "")
        assert "5 minutes" in error_msg
    finally:
        client.app.dependency_overrides.pop(get_login_failed_attempts_tracker, None)


def test_magic_link_dispatch_new_user(client, test_db):
    """
    Test requesting a magic link for a new email automatically provisions
    the user and dispatches an email via Resend mock.
    """
    res = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "newuser-magic@example.com"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert "Magic sign-in link dispatched" in res.json()["message"]


def test_magic_link_dispatch_existing_user(client, test_db):
    """
    Test requesting a magic link for an existing user account.
    """
    # Register user first
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "existing-magic@example.com", "password": "Password123!"},
    )
    assert reg_res.status_code == status.HTTP_201_CREATED

    res = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "existing-magic@example.com"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert "Magic sign-in link dispatched" in res.json()["message"]


def test_login_unverified_email_blocked_when_verification_required(client, test_db):
    """
    When REQUIRE_EMAIL_VERIFICATION is True, unverified registered users must be blocked with 403.
    """
    settings.REQUIRE_EMAIL_VERIFICATION = True
    try:
        client.post(
            "/api/v1/auth/register",
            json={"email": "unverified@example.com", "password": "SecurePassword123!"},
        )

        res = client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@example.com", "password": "SecurePassword123!"},
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert res.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    finally:
        settings.REQUIRE_EMAIL_VERIFICATION = False


def test_resend_verification_endpoint_success(client, test_db):
    """
    Test resend verification endpoint dispatches successfully.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "resend-test@example.com", "password": "SecurePassword123!"},
    )

    res = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "resend-test@example.com"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert "dispatched" in res.json()["message"].lower()
