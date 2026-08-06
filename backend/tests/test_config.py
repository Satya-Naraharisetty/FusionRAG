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
