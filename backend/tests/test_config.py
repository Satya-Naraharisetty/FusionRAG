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
        QDRANT_HOST="localhost"
    )
    assert settings.PROJECT_NAME == "Hybrid RAG Chatbot"
    assert settings.DATABASE_URL == "postgresql://test_user:test_password@localhost:5432/test_database"
