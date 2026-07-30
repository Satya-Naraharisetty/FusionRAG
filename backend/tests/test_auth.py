import concurrent.futures

import pytest
from fastapi import status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.infrastructure.persistence.models import Base
from app.core.config import settings

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/hybrid_rag"


@pytest.fixture(scope="function")
def test_db(client):
    """
    Fixture to set up a clean Postgres test database connection,
    truncating users and sessions before each test runs.
    """
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Clean the tables to guarantee test isolation
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE refresh_sessions CASCADE;"))
        db.execute(text("TRUNCATE TABLE users CASCADE;"))
        db.commit()
    finally:
        db.close()

    # Wire our test database session factory into the application state
    client.app.state.db_session_factory = SessionLocal

    yield SessionLocal


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
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


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


def test_refresh_concurrency_fails(client, test_db):
    """
    Test two simultaneous refresh requests using the same refresh token.
    Exactly one request must succeed, and the other must trigger reuse/revocation and fail.
    """
    client.post(
        "/api/v1/auth/register",
        json={"email": "concurrent@example.com", "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "concurrent@example.com", "password": "SecurePassword123!"},
    )
    cookie_v1 = login_res.cookies[settings.COOKIE_NAME]

    def do_refresh():
        from fastapi.testclient import TestClient

        from app.main import app

        thread_client = TestClient(app)
        thread_client.app.state.db_session_factory = client.app.state.db_session_factory
        thread_client.cookies.set(settings.COOKIE_NAME, cookie_v1)
        return thread_client.post("/api/v1/auth/refresh")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(do_refresh) for _ in range(2)]
        results = [f.result() for f in futures]

    # Exactly one request must succeed (200 OK), and one must fail (401)
    status_codes = [r.status_code for r in results]
    assert 200 in status_codes
    assert 401 in status_codes
