from app.core.config import Settings


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
    settings = Settings(
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_database",
        REDIS_HOST="localhost",
        QDRANT_HOST="localhost",
    )

    origins = settings.BACKEND_CORS_ORIGINS

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
