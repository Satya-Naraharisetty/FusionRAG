import json
import os
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
    POSTGRES_SERVER: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, info: ValidationInfo) -> Any:
        if isinstance(v, str) and v.strip():
            db_url = v.strip()
            if "pgbouncer=" in db_url.lower():
                from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

                parsed = urlparse(db_url)
                qsl = [
                    (k, v)
                    for k, v in parse_qsl(parsed.query)
                    if k.lower() != "pgbouncer"
                ]
                db_url = urlunparse(parsed._replace(query=urlencode(qsl)))
            return db_url
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
                f"PostgreSQL configurations (either set DATABASE_URL or set individual POSTGRES_* config): {missing_str}"
            )

        return f"postgresql://{data.get('POSTGRES_USER')}:{data.get('POSTGRES_PASSWORD')}@{data.get('POSTGRES_SERVER')}:{data.get('POSTGRES_PORT')}/{data.get('POSTGRES_DB')}"

    # Redis Configurations
    REDIS_HOST: str | None = None
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False
    REDIS_URL: str | None = None

    # Qdrant Vector DB Configurations
    QDRANT_HOST: str | None = None
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"
    QDRANT_API_KEY: str | None = None
    QDRANT_URL: str | None = None

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

    @field_validator("COOKIE_DOMAIN", mode="before")
    @classmethod
    def assemble_cookie_domain(cls, v: Any) -> str | None:
        if isinstance(v, str):
            val = v.strip()
            return val if val else None
        return v

    @field_validator("COOKIE_SAMESITE", mode="before")
    @classmethod
    def assemble_cookie_samesite(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().lower()
            if val in ("lax", "strict", "none"):
                return val
        return "lax"

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
    STORAGE_PROVIDER: str = "database"  # database | local | s3
    S3_BUCKET: str = "hybrid-rag-documents"
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    S3_REGION_NAME: str | None = None

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

    # Hybrid Search Settings
    ENABLE_HYBRID_SEARCH: bool = True
    ENABLE_MMR: bool = True
    ENABLE_RERANKER: bool = True
    BM25_TOP_K: int = 20
    VECTOR_TOP_K: int = 20
    RRF_K: int = 60
    MMR_LAMBDA: float = 0.5
    RERANK_TOP_K: int = 5

    # LLM Orchestration & Answer Generation Configurations
    LLM_PROVIDER: str = "gemini"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    GEMINI_CHAT_MODEL: str = "gemini-2.5-flash-lite"
    TEMPERATURE: float = 0.0
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_RESPONSE_TOKENS: int = 1000
    SYSTEM_PROMPT_PATH: str = "app/core/prompts/system_prompt.txt"
    SYSTEM_PROMPT_TOKENS: int = 1000
    RESERVED_COMPLETION_TOKENS: int = 500
    ENABLE_STREAMING: bool = True
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Conversation Memory & History-Aware Retrieval Configurations
    ENABLE_CONVERSATION_MEMORY: bool = True
    ENABLE_HISTORY_REWRITE: bool = True
    ENABLE_MEMORY_SUMMARIZATION: bool = True
    MAX_MESSAGES_PER_CONTEXT: int = 12
    MAX_MEMORY_TOKENS: int = 3000
    SUMMARY_TRIGGER_MESSAGES: int = 20
    SUMMARY_MAX_TOKENS: int = 400
    MAX_CONVERSATION_AGE_DAYS: int = 90

    # Agentic Tool Calling Configurations
    ENABLE_TOOL_CALLING: bool = True
    MAX_TOOL_ITERATIONS: int = 5
    MAX_TOOLS_PER_REQUEST: int = 10
    TOOL_EXECUTION_TIMEOUT: float = 30.0
    TOOL_RESULT_SIZE_LIMIT: int = 50000
    TOOL_OBSERVABILITY_ENABLED: bool = True
    TOOL_AUTO_RETRY_COUNT: int = 1
    TOOL_RECURSION_PROTECTION: bool = True

    # Evaluation & Benchmarking Configurations
    ENABLE_EVALUATION: bool = True
    ENABLE_RAGAS: bool = True
    ENABLE_DEEPEVAL: bool = True
    EVALUATION_PROVIDER: str = "gemini"
    ENABLE_GOLDEN_DATASETS: bool = True
    ENABLE_REGRESSION_TESTS: bool = True
    ENABLE_AGENT_EVALUATION: bool = True
    ENABLE_TOOL_EVALUATION: bool = True
    ENABLE_CONVERSATION_EVALUATION: bool = True
    MAX_EVALUATION_CONCURRENCY: int = 4
    SAVE_EVALUATION_RESULTS: bool = True
    EVALUATION_RESULTS_DIR: str = "data/evaluation"

    # Default quality thresholds
    THRESHOLD_FAITHFULNESS: float = 0.90
    THRESHOLD_ANSWER_RELEVANCY: float = 0.88
    THRESHOLD_CONTEXT_PRECISION: float = 0.85
    THRESHOLD_CONTEXT_RECALL: float = 0.85

    # Environment Profile configuration
    ENV: str = os.getenv("ENV", "development").lower()

    # Redis Cache Settings
    REDIS_CACHE_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_DEFAULT: int = 3600
    CACHE_TTL_RETRIEVAL: int = 1800
    CACHE_TTL_EMBEDDING: int = 86400
    CACHE_TTL_LLM: int = 3600
    CACHE_TTL_REWRITE: int = 7200
    CACHE_TTL_TOOL: int = 600
    CACHE_TTL_EVAL: int = 3600

    # Distributed Lock settings
    LOCK_TIMEOUT_DEFAULT: float = 10.0
    LOCK_RETRY_INTERVAL: float = 0.1

    # Rate Limiting settings
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # Reliability settings
    LLM_PROVIDER_BACKUP: str = "openai"
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 30.0
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0
    TIMEOUT_LLM: float = 15.0
    TIMEOUT_EMBEDDING: float = 5.0
    TIMEOUT_RETRIEVAL: float = 3.0

    # Task Queue Config
    TASK_QUEUE_PROVIDER: str = "in_process"  # in_process | celery | rq
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    WORKER_CONCURRENCY: int = 4

    # Security settings
    MALWARE_SCANNER_URL: str = ""
    SECRET_MANAGER_PROVIDER: str = "env"  # env | vault | aws
    MAX_CONTENT_LENGTH: int = 25 * 1024 * 1024  # 25 MB

    # Observability
    ENABLE_OTEL_TRACING: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    PROMETHEUS_MULTIPROC_DIR: str | None = None

    # Feature Flags
    ENABLE_SEMANTIC_CACHE: bool = True
    ENABLE_DISTRIBUTED_LOCKS: bool = True
    ENABLE_RATE_LIMITER: bool = True
    ENABLE_RESOURCE_QUOTAS: bool = True

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=[
            os.path.join(
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
                ".env.testing" if os.getenv("ENV", "").lower() == "testing" else ".env",
            ),
            os.path.join(
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..")
                ),
                ".env.testing" if os.getenv("ENV", "").lower() == "testing" else ".env",
            ),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instantiate settings singleton
settings = Settings()
