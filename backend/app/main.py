import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.evaluation import router as evaluation_router
from app.api.v1.health import router as health_router
from app.api.v1.observability import router as observability_router
from app.api.v1.search import router as search_router
from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    InvalidCredentialsException,
    InvalidSessionException,
    UserNotFoundException,
)
from app.auth.infrastructure.crypto.token_provider import JWTTokenProvider
from app.chat.domain.exceptions import (
    LLMProviderError,
    NoRelevantContext,
    PromptTooLarge,
    StreamingCancelled,
    TokenBudgetExceeded,
)
from app.core.config import ConfigurationError, settings
from app.core.context.request_context import RequestContext, current_request_context

# Run centralized logging configuration setup before other imports
from app.core.logger import (
    client_ip_ctx,
    request_duration_ctx,
    request_id_ctx,
    request_method_ctx,
    request_path_ctx,
    request_status_ctx,
    setup_logging,
)
from app.core.security import PromptInjectionError

# Register every ORM model on Base.metadata at import time.
# Without this, the chat tables (conversations, conversation_messages,
# conversation_summaries) referenced by the documents.conversation_id FK
# are missing and any Document flush crashes with NoReferencedTableError.
from app.db.models import Base  # noqa: F401  (side-effect: full model registration)
from app.documents.domain.exceptions import (
    DocumentCorrupted,
    DocumentExtractionFailed,
    DocumentNotFound,
    DocumentProcessingInProgressException,
    DocumentTooLarge,
    DuplicateDocumentException,
    InvalidStateTransitionException,
    UnauthorizedDocumentAccess,
    UnsupportedDocumentType,
)

setup_logging(settings.LOG_FORMAT, settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# 1. Startup validations


def run_startup_validations() -> None:
    """
    Validates that required system settings are non-empty and well-formed.
    """
    logger.info("Auditing environment settings configurations...")

    # Validate core infrastructure parameters
    infra_vars: dict[str, str | None] = {
        "JWT_SECRET": settings.JWT_SECRET,
    }
    if not settings.DATABASE_URL:
        infra_vars["POSTGRES_SERVER"] = settings.POSTGRES_SERVER
        infra_vars["POSTGRES_DB"] = settings.POSTGRES_DB

    # Dynamically validate S3 settings if storage provider is S3
    if settings.STORAGE_PROVIDER.lower() == "s3":
        infra_vars["S3_BUCKET"] = getattr(settings, "S3_BUCKET", None)

    empty_infra = [k for k, v in infra_vars.items() if not v or not str(v).strip()]

    # On Vercel serverless, skip presence checks for Redis and Qdrant — these
    # services are validated lazily at first use and their absence at boot
    # must not prevent the ASGI app from starting (which would also suppress
    # all CORS headers and present as a CORS error in the browser).
    import os as _os

    if _os.getenv("VERCEL") != "1":
        # Validate Redis config
        if not settings.REDIS_URL and not settings.REDIS_HOST:
            empty_infra.append("REDIS_HOST or REDIS_URL")

        # Validate Qdrant config
        if not settings.QDRANT_URL and not settings.QDRANT_HOST:
            empty_infra.append("QDRANT_HOST or QDRANT_URL")

    if empty_infra:
        raise ConfigurationError(
            f"Startup aborted due to empty required infrastructure parameters: "
            f"{', '.join(empty_infra)}"
        )

    # Validate API keys based on configured providers
    key_vars: dict[str, str | None] = {
        "GEMINI_FALLBACK_API_KEY": settings.get_gemini_fallback_api_key()
        or settings.GEMINI_LLM_API_KEY
    }

    empty_keys = [k for k, v in key_vars.items() if not v or not str(v).strip()]
    if empty_keys:
        msg = f"Empty required API key parameters: {', '.join(empty_keys)}"
        # On Vercel the app must boot so CORS preflight responses are served;
        # missing keys are downgraded to a warning and calls will fail at
        # request time rather than silently blocking all cross-origin requests.
        if settings.is_production and _os.getenv("VERCEL") != "1":
            raise ConfigurationError(f"Startup aborted due to: {msg}")
        else:
            logger.warning(
                f"{msg}. This is allowed in development mode, but LLM or cloud embedding calls will fail."
            )


async def verify_postgres_connectivity(engine) -> None:
    """
    Verifies that the PostgreSQL database container is online and accepting connections.
    """
    import os

    if (
        settings.is_testing
        or os.getenv("VERCEL") == "1"
        or type(engine).__name__ in ("MagicMock", "Mock")
    ):
        logger.info("Skipping PostgreSQL connectivity check.")
        return

    logger.info("Testing PostgreSQL connection readiness...")
    for attempt in range(1, 6):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL database connection verified.")
            return
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection verification attempt {attempt}/5 failed: {e}. "
                "Retrying in 2.0 seconds..."
            )
            if attempt < 5:
                await asyncio.sleep(2.0)

    raise ConfigurationError("PostgreSQL database connection could not be established.")


async def verify_alembic_migrations(engine) -> None:
    """
    Verifies that the database schema is up-to-date with the latest Alembic migration.
    Fails startup if it isn't.
    """
    import os

    if (
        settings.is_testing
        or os.getenv("VERCEL") == "1"
        or os.getenv("SKIP_DB_MIGRATION_CHECK", "false").lower() in ("true", "1", "yes")
        or type(engine).__name__ in ("MagicMock", "Mock")
    ):
        logger.info("Skipping database migration check.")
        return

    logger.info("Verifying database schema migrations are up-to-date...")
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "alembic.ini")
        if not os.path.exists(ini_path):
            logger.warning(
                f"Alembic config not found at {ini_path}. Skipping migration check."
            )
            return

        config = Config(ini_path)
        script = ScriptDirectory.from_config(config)
        head_revision = script.get_current_head()

        if not head_revision:
            logger.info("No migrations defined. Skipping migration check.")
            return
    except Exception as e:
        logger.warning(
            f"Could not load Alembic config or migrations: {e}. Skipping check."
        )
        return

    def get_revision(conn):
        context = MigrationContext.configure(conn)
        return context.get_current_revision()

    try:
        async with engine.connect() as conn:
            current_revision = await conn.run_sync(get_revision)
    except Exception as e:
        raise ConfigurationError(
            f"Database migrations check failed. Unable to read current revision: {e}"
        ) from e

    logger.info(
        f"Database migration check: DB revision={current_revision}, Code head revision={head_revision}"
    )
    if current_revision != head_revision:
        raise ConfigurationError(
            f"Database schema is out of date. Current DB revision: {current_revision}, "
            f"Latest application migration head: {head_revision}. "
            "Please run migrations using scripts/migrate.sh."
        )


# 2. Lifespan context manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup phase
    try:
        app.state.is_draining = False
        app.state.active_requests_count = 0
        app.state.request_count = 0
        app.state.error_count = 0
        app.state.started_at = time.time()

        run_startup_validations()

        # Initialize clients & save to app.state
        from app.db.session import (
            init_postgres_engine,
            init_qdrant_client,
            init_redis_client,
        )

        engine = init_postgres_engine(settings.DATABASE_URL or "")
        await verify_postgres_connectivity(engine)
        await verify_alembic_migrations(engine)

        app.state.db_engine = engine
        app.state.db_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        # Seed and enforce single default admin user from environment settings if configured
        if not settings.is_testing and settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
            logger.info("Enforcing single default admin account seeding...")
            async with app.state.db_session_factory() as db_session:
                try:
                    from sqlalchemy import select, update

                    from app.auth.infrastructure.crypto.password_hasher import (
                        Argon2PasswordHasher,
                    )
                    from app.auth.infrastructure.persistence.models import (
                        SQLAlchemyUser,
                    )

                    email = settings.ADMIN_EMAIL.strip().lower()

                    # 1. Demote any other admin users to "user" to maintain single admin constraint
                    await db_session.execute(
                        update(SQLAlchemyUser)
                        .where(
                            SQLAlchemyUser.role == "admin",
                            SQLAlchemyUser.email != email,
                        )
                        .values(role="user")
                    )

                    # 2. Check if the configured admin user exists
                    existing_admin_res = await db_session.execute(
                        select(SQLAlchemyUser).where(SQLAlchemyUser.email == email)
                    )
                    existing_admin = existing_admin_res.scalar_one_or_none()

                    if not existing_admin:
                        hasher = Argon2PasswordHasher()
                        hashed_pwd = hasher.hash(settings.ADMIN_PASSWORD)
                        new_admin = SQLAlchemyUser(
                            id=uuid.uuid4(),
                            email=email,
                            hashed_password=hashed_pwd,
                            role="admin",
                            is_active=True,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                        db_session.add(new_admin)
                        logger.info(
                            f"Successfully seeded default admin account: {email}"
                        )
                    else:
                        if existing_admin.role != "admin":
                            existing_admin.role = "admin"
                            logger.info(
                                f"Successfully promoted existing user {email} to admin."
                            )

                    await db_session.commit()
                except Exception as e:
                    logger.error(f"Failed to seed/enforce default admin account: {e}")
                    await db_session.rollback()

        app.state.redis = init_redis_client(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            url=settings.REDIS_URL,
        )
        app.state.qdrant = init_qdrant_client(
            settings.QDRANT_HOST,
            settings.QDRANT_PORT,
            settings.QDRANT_API_KEY,
            settings.QDRANT_URL,
        )

        # Verify S3 connection if using S3
        if settings.STORAGE_PROVIDER.lower() == "s3":
            from app.api.dependencies import get_storage_provider

            logger.info("Verifying S3 storage connectivity...")
            storage_provider = get_storage_provider(db=None)
            storage_provider.verify_connection()
            logger.info("S3 storage connection verified.")

        # Trigger background recovery of pending/failed durable cleanup jobs
        from app.documents.services.cleanup_worker import run_durable_cleanup_recovery

        run_durable_cleanup_recovery()

        # Warm up cross-encoder reranker if enabled (non-fatal graceful degradation on warmup error)
        if getattr(settings, "ENABLE_RERANKER", False) and not settings.is_testing:
            try:
                from app.api.dependencies import get_reranker

                reranker = get_reranker()
                if hasattr(reranker, "ensure_model_loaded"):
                    logger.info(
                        "Pre-warming CrossEncoder reranker model during application startup..."
                    )
                    reranker.ensure_model_loaded()
            except Exception as re_err:
                logger.warning(
                    f"Reranker model warmup encountered error during startup: {re_err}. "
                    "Application startup will proceed with graceful fallback to MMR order."
                )

        # Initialize DurableTaskQueue, JobDispatcher, and registered handlers
        from app.api.dependencies import (
            get_embedding_generator,
            get_extractor_factory,
            get_index_cache,
            get_llm_provider,
            get_storage_provider,
            get_vector_store,
        )
        from app.core.queue import (
            GenerateEmbeddingsJobHandler,
            InMemoryDurableTaskQueue,
            JobDispatcher,
            ProcessDocumentJobHandler,
            QueueWorker,
            RedisStreamTaskQueue,
            SummarizeConversationJobHandler,
        )

        dispatcher = JobDispatcher()
        storage_provider = (
            get_storage_provider(db=None)
            if settings.STORAGE_PROVIDER.lower() != "database"
            else None
        )
        extractor_factory = get_extractor_factory()
        index_cache = get_index_cache()

        if settings.is_testing or settings.QUEUE_TYPE == "in_memory":
            durable_queue: Any = InMemoryDurableTaskQueue(
                dispatcher=dispatcher, auto_dispatch=True
            )
        else:
            durable_queue = RedisStreamTaskQueue(
                redis_client=app.state.redis,
                stream_name=settings.QUEUE_STREAM_NAME,
                consumer_group=settings.QUEUE_CONSUMER_GROUP,
            )

        dispatcher.register(
            "PROCESS_DOCUMENT",
            ProcessDocumentJobHandler(
                db_session_factory=lambda: app.state.db_session_factory,
                storage_provider=storage_provider,
                extractor_factory=extractor_factory,
                task_queue=durable_queue,
                index_cache=index_cache,
            ),
        )
        dispatcher.register(
            "GENERATE_EMBEDDINGS",
            GenerateEmbeddingsJobHandler(
                db_session_factory=lambda: app.state.db_session_factory,
                embedding_generator=get_embedding_generator,
                vector_store=get_vector_store,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                provider_name=settings.EMBEDDING_PROVIDER,
                model_name=settings.effective_embedding_model,
                dimension=settings.effective_embedding_dimension,
                embedding_version=settings.EMBEDDING_VERSION,
            ),
        )
        dispatcher.register(
            "SUMMARIZE_CONVERSATION",
            SummarizeConversationJobHandler(
                db_session_factory=lambda: app.state.db_session_factory,
                llm_provider=get_llm_provider,
                model=settings.GEMINI_CHAT_MODEL,
                summary_trigger_messages=settings.SUMMARY_TRIGGER_MESSAGES,
                max_messages_per_context=settings.MAX_MESSAGES_PER_CONTEXT,
                summary_max_tokens=settings.SUMMARY_MAX_TOKENS,
            ),
        )

        app.state.durable_task_queue = durable_queue
        app.state.job_dispatcher = dispatcher

        if not settings.is_testing and isinstance(durable_queue, RedisStreamTaskQueue):
            worker = QueueWorker(
                task_queue=durable_queue,
                dispatcher=dispatcher,
                concurrency=settings.QUEUE_WORKER_CONCURRENCY,
                block_ms=settings.QUEUE_WORKER_BLOCK_MS,
                visibility_timeout_s=settings.QUEUE_VISIBILITY_TIMEOUT_SECONDS,
                retry_base_delay=settings.QUEUE_BASE_BACKOFF_SECONDS,
                retry_max_delay=settings.QUEUE_MAX_BACKOFF_SECONDS,
            )
            await worker.start()
            app.state.queue_worker = worker

            # Durable Ingestion Reaper (Phase 2.5.5)
            from app.documents.services.ingestion_reaper import DurableIngestionReaper

            reaper = DurableIngestionReaper(
                session_factory=app.state.db_session_factory,
                task_queue=durable_queue,
                stale_threshold_seconds=settings.INGESTION_REAPER_STALE_THRESHOLD_SECONDS,
            )
            # Run immediate startup recovery pass
            try:
                recovered_count = await reaper.reap()
                if recovered_count > 0:
                    logger.info(
                        f"Startup ingestion reaper recovered {recovered_count} stale documents."
                    )
            except Exception as reaper_err:
                logger.error(f"Startup ingestion reaper pass error: {reaper_err}")

            reaper_stop_event = asyncio.Event()
            app.state.reaper_stop_event = reaper_stop_event
            app.state.reaper_task = asyncio.create_task(
                reaper.run_loop(
                    interval_seconds=settings.INGESTION_REAPER_INTERVAL_SECONDS,
                    stop_event=reaper_stop_event,
                )
            )

        logger.info(
            "Application lifespan initialization completed. Web service online."
        )
    except Exception as e:
        logger.critical(
            f"Application startup initialization failed: {e}", exc_info=True
        )
        # Raise RuntimeError to halt process boot cleanly
        raise RuntimeError(f"Startup failed: {e}") from e

    yield

    # Shutdown phase
    logger.info("Initiating shutdown cleanup...")
    try:
        app.state.is_draining = True

        # Gracefully stop DurableIngestionReaper if running
        if hasattr(app.state, "reaper_stop_event"):
            app.state.reaper_stop_event.set()
        if hasattr(app.state, "reaper_task"):
            app.state.reaper_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(app.state.reaper_task), timeout=2.0
                )
            except Exception:
                pass
            logger.info("DurableIngestionReaper stopped.")

        # Gracefully stop QueueWorker if running
        if hasattr(app.state, "queue_worker"):
            await app.state.queue_worker.stop(timeout_seconds=5.0)
            logger.info("QueueWorker gracefully stopped.")

        # Wait up to 10 seconds to drain active requests
        for _ in range(10):
            active = app.state.active_requests_count
            if active == 0:
                break
            logger.info(f"Waiting for {active} requests to drain...")
            await asyncio.sleep(1.0)

        if hasattr(app.state, "db_engine"):
            await app.state.db_engine.dispose()
            logger.info("PostgreSQL connection engine disposed.")
        if hasattr(app.state, "redis"):
            await app.state.redis.close()
            logger.info("Redis cache client closed.")
        logger.info("Lifespan connections clean up completed.")
    except Exception as e:
        logger.error(f"Error occurred during shutdown teardown: {e}", exc_info=True)


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# 3. Request ID middleware


class ProductionMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive middleware pipeline:
    - Graceful shutdown check (returns 503 if draining)
    - Correlation ID tracking (X-Request-ID)
    - RequestContext initialization (ContextVar with immutable defaults)
    - Secure Headers injection
    - Structured Logging contexts
    - Response Timing
    """

    async def dispatch(self, request: Request, call_next):
        # 1. Graceful shutdown check
        if getattr(request.app.state, "is_draining", False):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "error": {
                        "code": "SERVICE_DRAINING",
                        "message": "Server is shutting down.",
                    }
                },
            )

        # Track active requests
        try:
            request.app.state.active_requests_count += 1
        except AttributeError:
            request.app.state.active_requests_count = 1
        request.app.state.request_count = (
            getattr(request.app.state, "request_count", 0) + 1
        )

        # 2. Resolve request ID
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # 3. Resolve JWT token and populate RequestContext
        user_id = None
        role = None
        permissions = []
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                token_provider = JWTTokenProvider()
                claims = token_provider.decode_token(token)
                user_id = claims.get("sub")
                role = claims.get("role")
                permissions = claims.get("permissions", [])
            except Exception:
                pass

        context = RequestContext(
            user_id=user_id,
            role=role,
            request_id=req_id,
            client_ip=request.client.host if request.client else None,
            permissions=permissions,
            tenant_id=request.headers.get("X-Tenant-ID"),
        )

        # Set ContextVar
        ctx_token = current_request_context.set(context)

        # Set Logger ContextVars
        request_id_ctx.set(req_id)
        request_method_ctx.set(request.method)
        request_path_ctx.set(request.url.path)
        client_ip_ctx.set(context.client_ip)

        start_time = time.perf_counter()

        try:
            logger.info("Request processing started")
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            request_status_ctx.set(response.status_code)
            request_duration_ctx.set(round(duration_ms, 2))
            if response.status_code >= 500:
                request.app.state.error_count = (
                    getattr(request.app.state, "error_count", 0) + 1
                )

            logger.info(f"Request processing completed - Duration: {duration_ms:.2f}ms")

            # Inject correlation ID and Secure Headers
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; frame-ancestors 'none'; object-src 'none';"
            )

            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            request_status_ctx.set(500)
            request_duration_ctx.set(round(duration_ms, 2))
            logger.exception(f"Request crashed during execution: {e}")
            raise e
        finally:
            current_request_context.reset(ctx_token)
            request.app.state.active_requests_count = max(
                0, request.app.state.active_requests_count - 1
            )


app.add_middleware(ProductionMiddleware)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=settings.BACKEND_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Global exception handlers


def format_error_response(
    code: str, message: str, details: Any = None, status_code: int = 500
) -> JSONResponse:
    req_id = request_id_ctx.get() or "N/A"
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": req_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    return format_error_response(
        code="HTTP_ERROR", message=exc.detail, status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    return format_error_response(
        code="VALIDATION_ERROR",
        message="Request parameters or body payload failed schema validations.",
        details=jsonable_encoder(exc.errors()),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(
    _request: Request, exc: ValidationError
):
    return format_error_response(
        code="VALIDATION_ERROR",
        message="Data validation checks failed.",
        details=jsonable_encoder(exc.errors()),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(DuplicateAccountException)
async def duplicate_account_exception_handler(
    _request: Request, exc: DuplicateAccountException
):
    logger.info("Registration rejected: email already registered")
    return format_error_response(
        code="DUPLICATE_ACCOUNT",
        message="An account with this email address already exists.",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.exception_handler(InvalidCredentialsException)
async def invalid_credentials_exception_handler(
    _request: Request, exc: InvalidCredentialsException
):
    logger.info(f"Failed authentication: {exc}")
    return format_error_response(
        code="INVALID_CREDENTIALS",
        message="Invalid email or password.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@app.exception_handler(AccountDisabledException)
async def account_disabled_exception_handler(
    _request: Request, exc: AccountDisabledException
):
    logger.info("Action blocked: account has been deactivated.")
    return format_error_response(
        code="ACCOUNT_DISABLED",
        message="Account has been deactivated.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@app.exception_handler(UserNotFoundException)
async def user_not_found_exception_handler(
    _request: Request, exc: UserNotFoundException
):
    logger.info(f"Account operation rejected: {exc}")
    return format_error_response(
        code="USER_NOT_FOUND",
        message="User account no longer exists.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


@app.exception_handler(InvalidSessionException)
async def invalid_session_exception_handler(
    _request: Request, exc: InvalidSessionException
):
    logger.info(f"Session validation rejected: {exc}")
    response = format_error_response(
        code="INVALID_SESSION",
        message="Session is invalid, expired, or has been revoked.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return response


@app.exception_handler(UnsupportedDocumentType)
async def unsupported_document_type_handler(
    _request: Request, exc: UnsupportedDocumentType
):
    return format_error_response(
        code="UNSUPPORTED_DOCUMENT_TYPE",
        message=str(exc),
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    )


@app.exception_handler(DocumentTooLarge)
async def document_too_large_handler(_request: Request, exc: DocumentTooLarge):
    return format_error_response(
        code="DOCUMENT_TOO_LARGE",
        message=str(exc),
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
    )


@app.exception_handler(DocumentNotFound)
async def document_not_found_handler(_request: Request, exc: DocumentNotFound):
    return format_error_response(
        code="DOCUMENT_NOT_FOUND",
        message=str(exc),
        status_code=status.HTTP_404_NOT_FOUND,
    )


@app.exception_handler(UnauthorizedDocumentAccess)
async def unauthorized_document_access_handler(
    _request: Request, exc: UnauthorizedDocumentAccess
):
    return format_error_response(
        code="UNAUTHORIZED_DOCUMENT_ACCESS",
        message=str(exc),
        status_code=status.HTTP_403_FORBIDDEN,
    )


@app.exception_handler(DuplicateDocumentException)
async def duplicate_document_exception_handler(
    _request: Request, exc: DuplicateDocumentException
):
    return format_error_response(
        code="DUPLICATE_DOCUMENT",
        message=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.exception_handler(DocumentCorrupted)
async def document_corrupted_handler(_request: Request, exc: DocumentCorrupted):
    return format_error_response(
        code="DOCUMENT_CORRUPTED",
        message=str(exc),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(DocumentExtractionFailed)
async def document_extraction_failed_handler(
    _request: Request, exc: DocumentExtractionFailed
):
    return format_error_response(
        code="DOCUMENT_EXTRACTION_FAILED",
        message=str(exc),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(InvalidStateTransitionException)
async def invalid_state_transition_handler(
    _request: Request, exc: InvalidStateTransitionException
):
    return format_error_response(
        code="INVALID_STATE_TRANSITION",
        message=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.exception_handler(DocumentProcessingInProgressException)
async def document_processing_in_progress_handler(
    _request: Request, exc: DocumentProcessingInProgressException
):
    return format_error_response(
        code="DOCUMENT_PROCESSING_IN_PROGRESS",
        message=str(exc),
        status_code=status.HTTP_409_CONFLICT,
    )


@app.exception_handler(NoRelevantContext)
async def no_relevant_context_handler(_request: Request, exc: NoRelevantContext):
    return format_error_response(
        code="NO_RELEVANT_CONTEXT",
        message=str(exc),
        status_code=status.HTTP_404_NOT_FOUND,
    )


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(_request: Request, exc: LLMProviderError):
    return format_error_response(
        code="LLM_PROVIDER_ERROR",
        message=str(exc),
        status_code=status.HTTP_502_BAD_GATEWAY,
    )


@app.exception_handler(PromptTooLarge)
async def prompt_too_large_handler(_request: Request, exc: PromptTooLarge):
    return format_error_response(
        code="PROMPT_TOO_LARGE",
        message=str(exc),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(TokenBudgetExceeded)
async def token_budget_exceeded_handler(_request: Request, exc: TokenBudgetExceeded):
    return format_error_response(
        code="TOKEN_BUDGET_EXCEEDED",
        message=str(exc),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(StreamingCancelled)
async def streaming_cancelled_handler(_request: Request, exc: StreamingCancelled):
    logger.info("Streaming client disconnected gracefully.")
    return format_error_response(
        code="STREAMING_CANCELLED",
        message=str(exc),
        status_code=499,
    )


@app.exception_handler(PromptInjectionError)
async def prompt_injection_handler(_request: Request, exc: PromptInjectionError):
    return format_error_response(
        code="PROMPT_INJECTION_DETECTED",
        message=str(exc),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.error(f"Unhandled system crash: {exc}", exc_info=True)
    return format_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected system error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


app.include_router(health_router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(conversations_router, prefix=f"{settings.API_V1_STR}/conversations")
app.include_router(evaluation_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(observability_router, prefix=settings.API_V1_STR)


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus scraping endpoint backed by live request counters."""
    request_count = getattr(app.state, "request_count", 0)
    error_count = getattr(app.state, "error_count", 0)
    active_requests = getattr(app.state, "active_requests_count", 0)
    started_at = getattr(app.state, "started_at", None)
    uptime = max(0.0, time.time() - started_at) if started_at else 0.0
    metrics_lines = [
        "# HELP http_requests_total Total HTTP requests processed",
        "# TYPE http_requests_total counter",
        f"http_requests_total {request_count}",
        "# HELP http_requests_failed_total HTTP requests returning 5xx responses",
        "# TYPE http_requests_failed_total counter",
        f"http_requests_failed_total {error_count}",
        "# HELP http_active_requests Current in-flight HTTP requests",
        "# TYPE http_active_requests gauge",
        f"http_active_requests {active_requests}",
        "# HELP process_uptime_seconds Seconds elapsed since application start",
        "# TYPE process_uptime_seconds gauge",
        f"process_uptime_seconds {uptime:.2f}",
    ]
    return Response(content="\n".join(metrics_lines) + "\n", media_type="text/plain")


@app.get("/")
def root_route():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API.",
        "health_liveness_endpoint": f"{settings.API_V1_STR}/health/liveness",
        "health_readiness_endpoint": f"{settings.API_V1_STR}/health/readiness",
    }
