import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.search import router as search_router
from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    InvalidCredentialsException,
    InvalidSessionException,
)
from app.chat.domain.exceptions import (
    NoRelevantContext,
    LLMProviderError,
    PromptTooLarge,
    TokenBudgetExceeded,
    StreamingCancelled,
)
from app.core.config import ConfigurationError, settings

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


# 2. Lifespan context manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup phase
    try:
        run_startup_validations()

        # Initialize clients & save to app.state
        from app.db.session import (
            init_postgres_engine,
            init_qdrant_client,
            init_redis_client,
        )

        engine = init_postgres_engine(settings.DATABASE_URL)
        verify_postgres_connectivity(engine)

        app.state.db_engine = engine
        app.state.db_session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )
        app.state.redis = init_redis_client(settings.REDIS_HOST, settings.REDIS_PORT)
        app.state.qdrant = init_qdrant_client(
            settings.QDRANT_HOST, settings.QDRANT_PORT
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


class RequestIdLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that captures or generates a unique correlation request ID,
    populates logging contexts, and attaches it to response headers.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Seed Thread-local contexts
        request_id_ctx.set(req_id)
        request_method_ctx.set(request.method)
        request_path_ctx.set(request.url.path)

        client_ip = request.client.host if request.client else None
        client_ip_ctx.set(client_ip)

        start_time = time.perf_counter()

        try:
            logger.info("Request processing started")
            response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000
            request_status_ctx.set(response.status_code)
            request_duration_ctx.set(round(duration_ms, 2))

            logger.info(f"Request processing completed - Duration: {duration_ms:.2f}ms")

            response.headers["X-Request-ID"] = req_id
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            request_status_ctx.set(500)
            request_duration_ctx.set(round(duration_ms, 2))

            logger.exception(f"Request crashed during execution: {e}")
            raise e


app.add_middleware(RequestIdLoggingMiddleware)

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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(
    _request: Request, exc: ValidationError
):
    return format_error_response(
        code="VALIDATION_ERROR",
        message="Data validation checks failed.",
        details=jsonable_encoder(exc.errors()),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@app.exception_handler(TokenBudgetExceeded)
async def token_budget_exceeded_handler(_request: Request, exc: TokenBudgetExceeded):
    return format_error_response(
        code="TOKEN_BUDGET_EXCEEDED",
        message=str(exc),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


@app.exception_handler(StreamingCancelled)
async def streaming_cancelled_handler(_request: Request, exc: StreamingCancelled):
    logger.info("Streaming client disconnected gracefully.")
    return format_error_response(
        code="STREAMING_CANCELLED",
        message=str(exc),
        status_code=499,
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


@app.get("/")
def root_route():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API.",
        "health_liveness_endpoint": f"{settings.API_V1_STR}/health/liveness",
        "health_readiness_endpoint": f"{settings.API_V1_STR}/health/readiness",
    }
