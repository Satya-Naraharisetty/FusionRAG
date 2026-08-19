import pytest

from app.core.config import ConfigurationError, Settings


def test_settings_parsing():
    """
    Asserts that configuration settings are parsed and build the Database URL correctly.
    """
    settings = Settings(
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
        DATABASE_URL=None,
    )
    assert settings.PROJECT_NAME == "Hybrid RAG Chatbot"
    assert (
        settings.DATABASE_URL
        == "postgresql://test_user:test_password@localhost:5432/test_database"
    )


def test_cors_origins_single_source_of_truth():
    """
    Pins the canonical CORS origin list defined in config.py.

    This list is the single source of truth - it must NOT be duplicated in
    docker-compose.yml or backend/.env. If the dev server port (5173) or the
    dockerized frontend (port 80) origins change, update this test AND the
    default in app/core/config.py together.
    """
    origins = Settings.model_fields["BACKEND_CORS_ORIGINS"].default

    # Vite dev server origins must always be allowed.
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins

    # Dockerized frontend (nginx on port 80) origins must always be allowed.
    assert "http://localhost" in origins
    assert "http://127.0.0.1" in origins

    # No duplicates.
    assert len(origins) == len(set(origins))


def test_cors_origins_accepts_env_override():
    """
    BACKEND_CORS_ORIGINS can still be overridden per-deployment via env var
    (JSON array or comma-separated) without touching the code default.
    """
    settings = Settings(
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
        BACKEND_CORS_ORIGINS='["https://app.example.com","https://api.example.com"]',
    )
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://app.example.com",
        "https://api.example.com",
    ]

    settings = Settings(
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
        BACKEND_CORS_ORIGINS="https://a.example.com,https://b.example.com",
    )
    assert settings.BACKEND_CORS_ORIGINS == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_supabase_url_parsing_and_pgbouncer_strip():
    """
    Asserts that DATABASE_URL is used directly and any pgbouncer parameter is stripped.
    """
    settings = Settings(
        DATABASE_URL="postgresql://user:pass@pooler.supabase.com:6543/db?pgbouncer=true&sslmode=require",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
    )
    assert (
        settings.DATABASE_URL
        == "postgresql://user:pass@pooler.supabase.com:6543/db?sslmode=require"
    )


def test_production_fails_when_secrets_missing():
    """
    Verify that in production mode (ENV=production), required secrets cannot be missing.
    """
    # 1. Missing Gemini key when gemini is active LLM provider
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is required"):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="a_very_long_secure_secret_signing_key_32_bytes_long",
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="",
        )

    # 2. Missing JWT secret
    with pytest.raises(ConfigurationError, match="JWT_SECRET is required"):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="",
            GEMINI_API_KEY="valid_key",
        )


def test_production_rejects_insecure_jwt_secret():
    """
    Verify that in production mode, short or placeholder JWT_SECRET is rejected.
    """
    # Too short
    with pytest.raises(
        ConfigurationError, match="JWT_SECRET must be at least 32 characters"
    ):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="short_secret",
            GEMINI_API_KEY="valid_key",
        )

    # Development placeholder
    with pytest.raises(
        ConfigurationError,
        match="JWT_SECRET contains an insecure development/testing placeholder",
    ):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="super_secure_random_development_signing_key_32_bytes_at_least",
            GEMINI_API_KEY="valid_key",
        )


def test_oauth_client_secret_required():
    """
    Verify that in production mode, if an OAuth client ID is set, the corresponding secret is required.
    """
    # Google OAuth ID set but secret missing
    with pytest.raises(ConfigurationError, match="GOOGLE_CLIENT_SECRET is required"):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="a_very_long_secure_secret_signing_key_32_bytes_long",
            GEMINI_API_KEY="valid_key",
            GOOGLE_CLIENT_ID="google_id",
            GOOGLE_CLIENT_SECRET="",
        )

    # GitHub OAuth ID set but secret missing
    with pytest.raises(ConfigurationError, match="GITHUB_CLIENT_SECRET is required"):
        Settings(
            ENV="production",
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="test_user",
            POSTGRES_PASSWORD="test_password",
            POSTGRES_DB="test_database",
            REDIS_HOST="localhost",
            QDRANT_HOST="localhost",
            JWT_SECRET="a_very_long_secure_secret_signing_key_32_bytes_long",
            GEMINI_API_KEY="valid_key",
            GITHUB_CLIENT_ID="github_id",
            GITHUB_CLIENT_SECRET="",
        )
