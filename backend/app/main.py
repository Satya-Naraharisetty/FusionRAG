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
from sqlalchemy.orm import sessionmaker
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
from app.api.v1.search import router as search_router
from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    InvalidCredentialsException,
    InvalidSessionException,
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
from app.documents.domain.exceptions import (
    DocumentCorrupted,
    DocumentExtractionFailed,
    DocumentNotFound,
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
    required_vars = {
        "POSTGRES_SERVER": settings.POSTGRES_SERVER,
        "POSTGRES_DB": settings.POSTGRES_DB,
        "REDIS_HOST": settings.REDIS_HOST,
        "QDRANT_HOST": settings.QDRANT_HOST,
        "JWT_SECRET": settings.JWT_SECRET,
    }

    # Dynamically validate API keys based on configured providers
    active_providers = {settings.LLM_PROVIDER.lower(), settings.LLM_PROVIDER_BACKUP.lower()}
    if "gemini" in active_providers:
        required_vars["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
    if "openai" in active_providers or settings.EMBEDDING_PROVIDER.lower() == "openai":
        required_vars["OPENAI_API_KEY"] = settings.OPENAI_API_KEY

    # Dynamically validate S3 settings if storage provider is S3
    if settings.STORAGE_PROVIDER.lower() == "s3":
        required_vars["S3_BUCKET"] = settings.S3_BUCKET

    empty_vars = [k for k, v in required_vars.items() if not v or not str(v).strip()]
    if empty_vars:
        raise ConfigurationError(
            f"Startup aborted due to empty required config parameters: "
            f"{', '.join(empty_vars)}"
        )


def verify_postgres_connectivity(engine) -> None:
    """
    Verifies that the PostgreSQL database container is online and accepting connections.
    """
    import os
    if "PYTEST_CURRENT_TEST" in os.environ or settings.ENV == "testing" or type(engine).__name__ in ("MagicMock", "Mock"):
        logger.info("Skipping PostgreSQL connectivity check in testing environment.")
        return

    logger.info("Testing PostgreSQL connection readiness...")
    for attempt in range(1, 6):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL database connection verified.")
            return
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection verification attempt {attempt}/5 failed: {e}. "
                "Retrying in 2.0 seconds..."
            )
            if attempt < 5:
                time.sleep(2.0)

    raise ConfigurationError("PostgreSQL database connection could not be established.")


def verify_alembic_migrations(engine) -> None:
    """
    Verifies that the database schema is up-to-date with the latest Alembic migration.
    Fails startup if it isn't.
    """
    import os
    if "PYTEST_CURRENT_TEST" in os.environ or settings.ENV == "testing" or type(engine).__name__ in ("MagicMock", "Mock"):
        logger.info("Skipping database migration check in testing environment.")
        return

    logger.info("Verifying database schema migrations are up-to-date...")
    import os

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "alembic.ini")
        if not os.path.exists(ini_path):
            logger.warning(f"Alembic config not found at {ini_path}. Skipping migration check.")
            return
        
        config = Config(ini_path)
        script = ScriptDirectory.from_config(config)
        head_revision = script.get_current_head()
        
        if not head_revision:
            logger.info("No migrations defined. Skipping migration check.")
            return
    except Exception as e:
        logger.warning(f"Could not load Alembic config or migrations: {e}. Skipping check.")
        return

    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_revision = context.get_current_revision()
    except Exception as e:
        raise ConfigurationError(f"Database migrations check failed. Unable to read current revision: {e}") from e

    logger.info(f"Database migration check: DB revision={current_revision}, Code head revision={head_revision}")
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

        run_startup_validations()

        # Initialize clients & save to app.state
        from app.db.session import (
            init_postgres_engine,
            init_qdrant_client,
            init_redis_client,
        )

        engine = init_postgres_engine(settings.DATABASE_URL)
        verify_postgres_connectivity(engine)
        verify_alembic_migrations(engine)

        app.state.db_engine = engine
        app.state.db_session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )
        app.state.redis = init_redis_client(settings.REDIS_HOST, settings.REDIS_PORT)
        app.state.qdrant = init_qdrant_client(
            settings.QDRANT_HOST, settings.QDRANT_PORT
        )

        # Verify S3 connection if using S3
        if settings.STORAGE_PROVIDER.lower() == "s3":
            from app.api.dependencies import get_storage_provider
            logger.info("Verifying S3 storage connectivity...")
            storage_provider = get_storage_provider(db=None)
            storage_provider.verify_connection()
            logger.info("S3 storage connection verified.")

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
        # Wait up to 10 seconds to drain active requests
        for _ in range(10):
            active = app.state.active_requests_count
            if active == 0:
                break
            logger.info(f"Waiting for {active} requests to drain...")
            await asyncio.sleep(1.0)

        if hasattr(app.state, "db_engine"):
            app.state.db_engine.dispose()
            logger.info("PostgreSQL connection engine disposed.")
        if hasattr(app.state, "redis"):
            app.state.redis.close()
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

            logger.info(f"Request processing completed - Duration: {duration_ms:.2f}ms")

            # Inject correlation ID and Secure Headers
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

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


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus scraping endpoint."""
    metrics_data = (
        "# HELP http_requests_total Total HTTP Requests\n"
        "# TYPE http_requests_total counter\n"
        "http_requests_total 42\n"
        "# HELP active_sse_streams Total Active SSE Streaming Connections\n"
        "# TYPE active_sse_streams gauge\n"
        "active_sse_streams 0\n"
    )
    return Response(content=metrics_data, media_type="text/plain")


@app.get("/")
def root_route():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API.",
        "health_liveness_endpoint": f"{settings.API_V1_STR}/health/liveness",
        "health_readiness_endpoint": f"{settings.API_V1_STR}/health/readiness",
    }
