import json
from typing import Any

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """
    Exception raised when configuration variables are missing or invalid.
    """

    pass


class Settings(BaseSettings):
    PROJECT_NAME: str = "Hybrid RAG Chatbot"
    API_V1_STR: str = "/api/v1"

    # PostgreSQL Configurations
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, info: ValidationInfo) -> Any:
        if isinstance(v, str) and v.strip():
            return v
        data = info.data

        # Verify required database connection credentials are provided
        required_fields = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_SERVER",
            "POSTGRES_PORT",
            "POSTGRES_DB",
        ]
        missing_fields = [
            f for f in required_fields if f not in data or data[f] is None
        ]
        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ConfigurationError(
                f"Cannot assemble DATABASE_URL due to missing "
                f"PostgreSQL configurations: {missing_str}"
            )

        return f"postgresql://{data.get('POSTGRES_USER')}:{data.get('POSTGRES_PASSWORD')}@{data.get('POSTGRES_SERVER')}:{data.get('POSTGRES_PORT')}/{data.get('POSTGRES_DB')}"

    # Redis Configurations
    REDIS_HOST: str
    REDIS_PORT: int = 6379

    # Qdrant Vector DB Configurations
    QDRANT_HOST: str
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"

    # Embedding Configurations
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_VERSION: str = "v1"

    # OpenAI API Configurations
    OPENAI_API_KEY: str = ""

    # CORS Configurations
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, (list, set, tuple)):
            return [str(x) for x in v]
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    # JWT & Cookie Configurations
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_NAME: str = "refresh_token"
    COOKIE_DOMAIN: str | None = None
    COOKIE_PATH: str = "/api/v1/auth"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    COOKIE_MAX_AGE: int = 7 * 24 * 60 * 60

    # Logging Configurations
    LOG_FORMAT: str = "TEXT"
    LOG_LEVEL: str = "INFO"

    # Ingestion & Upload Configurations
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE: int = 25 * 1024 * 1024  # 25 MB default

    # Chunking Configurations
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    MIN_CHUNK_SIZE: int = 50
    CHUNK_STRATEGY: str = "recursive"

    # Retrieval & Search Configurations
    DEFAULT_TOP_K: int = 10
    MAX_TOP_K: int = 100
    SIMILARITY_THRESHOLD: float = 0.25
    VECTOR_COLLECTION_NAME: str = "documents"
    SEARCH_TIMEOUT: float = 3.0

    # LLM Orchestration & Answer Generation Configurations
    LLM_PROVIDER: str = "gemini"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    GEMINI_CHAT_MODEL: str = "gemini-1.5-flash"
    TEMPERATURE: float = 0.0
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_RESPONSE_TOKENS: int = 1000
    SYSTEM_PROMPT_PATH: str = "app/core/prompts/system_prompt.txt"
    SYSTEM_PROMPT_TOKENS: int = 1000
    RESERVED_COMPLETION_TOKENS: int = 500
    ENABLE_STREAMING: bool = True
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=".env", env_file_encoding="utf-8"
    )


# Instantiate settings singleton
settings = Settings()
