import json
import os
from typing import Annotated, Any, Literal

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

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

    # Queue Configurations
    QUEUE_TYPE: str = "in_memory"  # "redis_stream" | "in_memory"
    QUEUE_STREAM_NAME: str = "stream:jobs:document_processing"
    QUEUE_CONSUMER_GROUP: str = "group:document_workers"
    QUEUE_DEAD_LETTER_STREAM: str = "stream:jobs:dead_letter"
    QUEUE_RETRY_SORTED_SET: str = "queue:jobs:retry"
    QUEUE_MAX_STREAM_LENGTH: int = 10000
    QUEUE_MAX_ATTEMPTS: int = 3
    QUEUE_BASE_BACKOFF_SECONDS: float = 2.0
    QUEUE_MAX_BACKOFF_SECONDS: float = 60.0
    QUEUE_VISIBILITY_TIMEOUT_SECONDS: int = 180
    QUEUE_WORKER_CONCURRENCY: int = 4
    QUEUE_WORKER_BLOCK_MS: int = 2000

    # Ingestion Reaper Configurations
    INGESTION_REAPER_INTERVAL_SECONDS: float = 60.0
    INGESTION_REAPER_STALE_THRESHOLD_SECONDS: float = 60.0

    # Sparse Retrieval Configurations
    SPARSE_RETRIEVER_TYPE: str = "postgres_fts"  # "postgres_fts" | "bm25_memory"

    # Qdrant Vector DB Configurations
    QDRANT_HOST: str | None = None
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "documents"
    QDRANT_API_KEY: str | None = None
    QDRANT_URL: str | None = None

    # Embedding Configurations
    # Default is Jina AI (jina-embeddings-v3) with 768 dimensions (Matryoshka representation).
    # Gemini (text-embedding-004) is also supported as an alternate provider.
    EMBEDDING_PROVIDER: str = "jina"
    EMBEDDING_MODEL: str = "jina-embeddings-v3"
    EMBEDDING_DIMENSION: int = 768
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_VERSION: str = "v1"

    @property
    def effective_embedding_dimension(self) -> int:
        """Return the configured embedding dimension."""
        return self.EMBEDDING_DIMENSION

    @property
    def effective_embedding_model(self) -> str:
        """Return the configured embedding model."""
        return self.EMBEDDING_MODEL

    # CORS Configurations
    # NoDecode disables pydantic-settings' eager JSON decoding so that both
    # comma-separated ("http://a,http://b") and JSON-array values are handled
    # by assemble_cors_origins below instead of raising SettingsError.
    #
    # SINGLE SOURCE OF TRUTH: this list is the canonical set of allowed CORS
    # origins. It must not be duplicated in docker-compose.yml, backend/.env,
    # or any other config file - per-deployment overrides via the
    # BACKEND_CORS_ORIGINS environment variable are supported, but the tracked
    # default here is what should be edited when origins change.
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        # Vite dev server
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Dockerized frontend (nginx on port 80)
        "http://localhost",
        "http://localhost:80",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        # Legacy / alternate local ports
        "http://localhost:8080",
    ]
    BACKEND_CORS_ORIGIN_REGEX: str | None = r"https://.*\.vercel\.app"

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
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_MAX_AGE: int = 7 * 24 * 60 * 60

    # Encryption Configuration
    ENCRYPTION_MASTER_KEY: str | None = None

    # Logging Configurations
    LOG_FORMAT: str = "TEXT"
    LOG_LEVEL: str = "INFO"

    # Observability & OpenTelemetry Configurations
    ENABLE_TELEMETRY: bool = True
    ENABLE_TRACING: bool = True
    ENABLE_PROMETHEUS_METRICS: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "hybrid-rag-backend"
    OTEL_TRACES_SAMPLER_RATIO: float = 1.0

    # Ingestion & Upload Configurations
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE: int = 25 * 1024 * 1024  # 25 MB default
    STORAGE_PROVIDER: Literal["database", "local"] = "database"

    # Malware Scanning Configurations
    MALWARE_SCANNER_TYPE: Literal["stub", "clamav"] = "stub"
    CLAMAV_HOST: str | None = None
    CLAMAV_PORT: int = 3310
    CLAMAV_TIMEOUT_SECONDS: float = 10.0
    MALWARE_SCAN_FAIL_CLOSED: bool = True

    # Chunking Configurations
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    MIN_CHUNK_SIZE: int = 50
    CHUNK_STRATEGY: str = "recursive"
    PARENT_CHUNK_SIZE: int = 1500
    PARENT_CHUNK_OVERLAP: int = 150
    CHILD_CHUNK_SIZE: int = 400
    CHILD_CHUNK_OVERLAP: int = 50
    SENTENCE_WINDOW_SIZE: int = 2

    # Retrieval & Search Configurations
    DEFAULT_TOP_K: int = 10
    MAX_TOP_K: int = 100
    SIMILARITY_THRESHOLD: float = 0.25
    VECTOR_COLLECTION_NAME: str = "documents"
    SEARCH_TIMEOUT: float = 3.0

    # Hybrid Search Settings
    ENABLE_HYBRID_SEARCH: bool = True
    # How long (seconds) the shared index cache holds a user's "no chunks yet"
    # determination before re-querying the DB. Bounds staleness when an upload
    # happens outside the normal invalidation path (direct DB writes, admin
    # tooling); uploads themselves invalidate the entry immediately.
    EMPTY_KB_CACHE_TTL_SECONDS: float = 60.0
    ENABLE_MMR: bool = True
    ENABLE_RERANKER: bool = True
    RERANKER_MODEL: str = "jina-reranker-v2-base-multilingual"
    RERANKER_PROVIDER: str = "jina"
    RERANKER_DEVICE: str = "cpu"
    RERANK_TOP_K: int = 5
    RERANKER_BATCH_SIZE: int = 16
    RERANKER_MAX_LENGTH: int = 512
    RERANKER_CONCURRENCY_LIMIT: int = 4
    JINA_API_KEY: str = ""
    BM25_TOP_K: int = 20
    VECTOR_TOP_K: int = 20
    RRF_K: int = 60
    MMR_LAMBDA: float = 0.5
    # Advanced RAG Configurations
    ENABLE_QUERY_CLASSIFICATION: bool = True
    ENABLE_QUERY_EXPANSION: bool = False
    QUERY_EXPANSION_MAX_QUERIES: int = 3
    QUERY_EXPANSION_TIMEOUT_MS: int = 500
    ENABLE_QUERY_DECOMPOSITION: bool = False
    MAX_QUERY_SUBTASKS: int = 3
    QUERY_DECOMPOSITION_TIMEOUT_MS: int = 500
    MAX_TOTAL_RETRIEVAL_QUERIES: int = 6
    DEFAULT_RETRIEVAL_TOP_K: int = 10
    EXPANDED_QUERY_TOP_K: int = 15
    MULTI_HOP_TOP_K: int = 20
    MAX_RETRIEVAL_CANDIDATES: int = 100
    ENABLE_WEIGHTED_RRF: bool = False
    DENSE_WEIGHT: float = 1.0
    SPARSE_WEIGHT: float = 1.0
    ENABLE_CONTEXT_SELECTION: bool = False
    CONTEXT_SCORE_SOURCE: Literal["rerank_score", "rrf_score", "similarity_score"] = (
        "rerank_score"
    )
    CONTEXT_MAX_TOKENS: int = 6000
    CONTEXT_MIN_CHUNK_SCORE: float = 0.0
    CONTEXT_MAX_CHUNKS: int = 12
    CONTEXT_ORDERING_STRATEGY: str = "rerank_score_desc"
    ENABLE_NEIGHBOR_CHUNKS: bool = False
    NEIGHBOR_CHUNK_WINDOW: int = 1
    ENABLE_PARENT_CHILD_RAG: bool = False
    ENABLE_SENTENCE_WINDOW_RAG: bool = False
    ENABLE_CONTEXTUAL_RETRIEVAL: bool = False
    TOTAL_ADVANCED_RAG_TIMEOUT_MS: int = 3000

    # Adaptive / Agentic RAG Orchestration Configurations
    ENABLE_ADAPTIVE_RAG: bool = False
    ENABLE_HYDE: bool = False
    HYDE_GENERATOR_TYPE: Literal["deterministic", "llm"] = "deterministic"
    HYDE_TIMEOUT_MS: int = 1000
    HYDE_MAX_TOKENS: int = 512
    HYDE_MAX_RETRIES: int = 1
    HYDE_MIN_QUERY_CONFIDENCE: float = 0.70
    HYDE_MAX_RETRIEVAL_CALLS: int = 1

    MAX_AGENT_ITERATIONS: int = 3
    MAX_AGENT_TASKS: int = 8
    MAX_AGENT_RETRIEVAL_CALLS: int = 12
    MAX_AGENT_REPLANS: int = 2
    AGENT_TOTAL_TIMEOUT_MS: int = 5000
    MAX_DUPLICATE_TASK_ATTEMPTS: int = 0

    # LLM Orchestration & Answer Generation Configurations
    LLM_PROVIDER: str = "gemini"
    GEMINI_CHAT_MODEL: str = "gemini-3.5-flash-lite"
    TEMPERATURE: float = 0.0
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_RESPONSE_TOKENS: int = 1000
    SYSTEM_PROMPT_PATH: str = "app/core/prompts/system_prompt.txt"
    SYSTEM_PROMPT_TOKENS: int = 1000
    RESERVED_COMPLETION_TOKENS: int = 500
    ENABLE_STREAMING: bool = True
    GEMINI_API_KEY: str = ""
    GEMINI_FALLBACK_API_KEY: str = ""
    GEMINI_EMBEDDING_API_KEY: str = ""
    GEMINI_LLM_API_KEY: str = ""

    def get_gemini_fallback_api_key(self) -> str:
        """Returns the fallback Gemini API key."""
        return (self.GEMINI_FALLBACK_API_KEY or self.GEMINI_API_KEY).strip()

    def get_gemini_embedding_api_key(self) -> str:
        """Returns the dedicated embedding Gemini API key, falling back to fallback key."""
        return (
            self.GEMINI_EMBEDDING_API_KEY
            or self.GEMINI_FALLBACK_API_KEY
            or self.GEMINI_API_KEY
        ).strip()

    def get_gemini_llm_api_key(self) -> str:
        """Returns the dedicated LLM Gemini API key, falling back to fallback key."""
        return (
            self.GEMINI_LLM_API_KEY
            or self.GEMINI_FALLBACK_API_KEY
            or self.GEMINI_API_KEY
        ).strip()

    def get_jina_api_key(self) -> str:
        """Returns the configured Jina API key."""
        return (self.JINA_API_KEY or "").strip()

    # OAuth (Google)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # OAuth (GitHub)
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    # Base URL of the backend used to build OAuth callback URIs.
    # Local: http://localhost:8000 | Production: https://hybrid-rag-gilt.vercel.app
    OAUTH_REDIRECT_BASE_URL: str = "http://localhost:8000"
    # Base URL of the frontend used to redirect after OAuth success/failure.
    # Local: http://localhost:5173 | Production: https://hybrid-rag-frontend.vercel.app
    FRONTEND_URL: str = "http://localhost:5173"

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

    # Multi-Agent Master-Worker Configurations
    ENABLE_MULTI_AGENT: bool = True
    MAX_PLAN_ITERATIONS: int = 2
    MAX_SPECIALIST_TASKS: int = 5
    MAX_TOTAL_AGENT_CALLS: int = 8
    MULTI_AGENT_TASK_TIMEOUT: float = 20.0

    # Research Planner Configurations (Prompt 3.3)
    RESEARCH_MAX_SUBQUERIES: int = 4
    RESEARCH_MAX_RETRIEVAL_CALLS: int = 6
    RESEARCH_QUERY_TIMEOUT: float = 10.0
    RESEARCH_DEDUP_SIMILARITY_THRESHOLD: float = 0.85
    RESEARCH_ENABLE_LLM_PLANNER: bool = True

    # Capability-Aware Routing Configurations (Prompt 3.4)
    CAPABILITY_ROUTING_ENABLED: bool = True
    ENABLE_LLM_CAPABILITY_ROUTER: bool = False
    MAX_ESTIMATED_AGENT_COST_UNITS: float = 100.0
    MAX_ESTIMATED_LATENCY_MS: float = 30000.0

    # Production Observability & Resilience Configurations (Prompt 3.5)
    AGENT_OBSERVABILITY_ENABLED: bool = True
    AGENT_TRACE_PERSISTENCE_ENABLED: bool = False
    AGENT_TRACE_MAX_EVENTS: int = 500
    AGENT_TRACE_MAX_TASKS: int = 50
    AGENT_TRACE_RETENTION_DAYS: int = 7
    AGENT_METRICS_ENABLED: bool = True
    AGENT_DETAILED_ERRORS: bool = False
    AGENT_RETRY_BACKOFF_BASE_MS: int = 100
    AGENT_RETRY_BACKOFF_MAX_MS: int = 2000
    AGENT_MAX_TELEMETRY_STRING_LEN: int = 500
    AGENT_MAX_TELEMETRY_METADATA_KEYS: int = 50

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

    # Default Admin Credentials Seeding
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    # Default quality thresholds
    THRESHOLD_FAITHFULNESS: float = 0.90
    THRESHOLD_ANSWER_RELEVANCY: float = 0.88
    THRESHOLD_CONTEXT_PRECISION: float = 0.85
    THRESHOLD_CONTEXT_RECALL: float = 0.85

    # Environment Profile configuration (defaults to 'development')
    ENV: str = "development"

    @property
    def is_production(self) -> bool:
        return self.ENV == "production" or os.getenv("VERCEL") == "1"

    @property
    def is_testing(self) -> bool:
        return self.ENV == "testing" or "PYTEST_CURRENT_TEST" in os.environ

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
    # Stricter per-user limit for the password-gated DELETE /auth/account so a
    # compromised access token cannot be used to brute-force the re-entry field.
    ACCOUNT_DELETE_RATE_LIMIT_PER_MINUTE: int = 10
    # Strict brute-force guard for /auth/login: max 5 attempts per 5 minutes (300s window)
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300  # 5 minutes (300 seconds)

    # Reliability settings
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

    # Observability Legacy Aliases & Extra
    PROMETHEUS_MULTIPROC_DIR: str | None = None

    # Feature Flags
    ENABLE_SEMANTIC_CACHE: bool = True
    ENABLE_DISTRIBUTED_LOCKS: bool = True
    ENABLE_RATE_LIMITER: bool = True
    ENABLE_RESOURCE_QUOTAS: bool = True

    INDEX_CACHE_MAX_USERS: int = 500
    CLEANUP_RECOVERY_BATCH_SIZE: int = 20

    @field_validator("INDEX_CACHE_MAX_USERS")
    @classmethod
    def validate_index_cache_max_users(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("INDEX_CACHE_MAX_USERS must be greater than zero.")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.is_production:
            # 1. JWT_SECRET checks
            if not getattr(self, "JWT_SECRET", None):
                raise ConfigurationError("JWT_SECRET is required in production.")

            jwt_sec = self.JWT_SECRET
            # Check length: sufficiently long (>= 32 bytes)
            if len(jwt_sec) < 32:
                raise ConfigurationError(
                    "JWT_SECRET must be at least 32 characters long in production."
                )

            # Known placeholders check
            known_placeholders = {
                "super_secure_random_development_signing_key_32_bytes_at_least",
                "testing_secret",
                "mock_secret",
                "ci_test_secret",
                "placeholder",
            }
            if jwt_sec.lower() in known_placeholders or any(
                p in jwt_sec.lower() for p in ["development", "testing", "mock"]
            ):
                raise ConfigurationError(
                    "JWT_SECRET contains an insecure development/testing placeholder in production."
                )

            # 2. LLM Provider keys
            # Gemini key check
            gemini_key = (
                getattr(self, "GEMINI_FALLBACK_API_KEY", "")
                or getattr(self, "GEMINI_API_KEY", "")
                or getattr(self, "GEMINI_LLM_API_KEY", "")
            )
            if not gemini_key or gemini_key.strip() in (
                "",
                "your_gemini_api_key_here",
            ):
                raise ConfigurationError(
                    "GEMINI_FALLBACK_API_KEY (or GEMINI_API_KEY / GEMINI_LLM_API_KEY) is required in production when Gemini is enabled."
                )

            # 2b. Jina API Key check
            if getattr(self, "EMBEDDING_PROVIDER", "") == "jina" or (
                getattr(self, "ENABLE_RERANKER", False)
                and getattr(self, "RERANKER_PROVIDER", "") == "jina"
            ):
                jina_key = getattr(self, "JINA_API_KEY", "")
                if not jina_key or jina_key.strip() in (
                    "",
                    "your_jina_api_key_here",
                ):
                    raise ConfigurationError(
                        "JINA_API_KEY is required in production when Jina embeddings or reranker is enabled."
                    )

            # 3. OAuth checks
            google_id = getattr(self, "GOOGLE_CLIENT_ID", "")
            google_secret = getattr(self, "GOOGLE_CLIENT_SECRET", "")
            if google_id and not google_secret:
                raise ConfigurationError(
                    "GOOGLE_CLIENT_SECRET is required when GOOGLE_CLIENT_ID is configured."
                )

            github_id = getattr(self, "GITHUB_CLIENT_ID", "")
            github_secret = getattr(self, "GITHUB_CLIENT_SECRET", "")
            if github_id and not github_secret:
                raise ConfigurationError(
                    "GITHUB_CLIENT_SECRET is required when GITHUB_CLIENT_ID is configured."
                )

            # 4. ENCRYPTION_MASTER_KEY check
            enc_key = getattr(self, "ENCRYPTION_MASTER_KEY", None)
            if not enc_key:
                raise ConfigurationError(
                    "ENCRYPTION_MASTER_KEY is required in production."
                )
            if len(enc_key) < 32:
                raise ConfigurationError(
                    "ENCRYPTION_MASTER_KEY must be at least 32 characters long in production."
                )
            if (
                enc_key.lower() in known_placeholders
                or "default-insecure" in enc_key.lower()
                or any(p in enc_key.lower() for p in ["development", "testing", "mock"])
            ):
                raise ConfigurationError(
                    "ENCRYPTION_MASTER_KEY contains an insecure placeholder in production."
                )

        return self

    def __repr__(self) -> str:
        sensitive_patterns = {"key", "secret", "password", "url"}
        public_fields = {}
        for k, v in self.__dict__.items():
            if any(pattern in k.lower() for pattern in sensitive_patterns) and v:
                public_fields[k] = "********"
            else:
                public_fields[k] = v
        field_reprs = [
            f"{k}={repr(v)}" for k, v in public_fields.items() if not k.startswith("_")
        ]
        return f"Settings({', '.join(field_reprs)})"

    def __str__(self) -> str:
        return self.__repr__()

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
settings = Settings()  # type: ignore[call-arg]  # populated from env by pydantic-settings
