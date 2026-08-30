import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth.domain.exceptions import (
    AccountDisabledException,
    DuplicateAccountException,
    EmailNotVerifiedException,
    ExpiredVerificationTokenException,
    InvalidCredentialsException,
    InvalidSessionException,
    InvalidVerificationTokenException,
    MaxVerificationAttemptsException,
    UserNotFoundException,
)
from app.chat.domain.exceptions import (
    LLMProviderError,
    NoRelevantContext,
    PromptTooLarge,
    StreamingCancelled,
    TokenBudgetExceeded,
)
from app.core.config import settings
from app.core.logger import request_id_ctx
from app.core.security import PromptInjectionError
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

logger = logging.getLogger(__name__)


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


def register_exception_handlers(app: FastAPI) -> None:
    """Register all domain and framework exception handlers onto the FastAPI app instance."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
        return format_error_response(
            code="HTTP_ERROR", message=exc.detail, status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ):
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

    @app.exception_handler(EmailNotVerifiedException)
    async def email_not_verified_exception_handler(
        _request: Request, exc: EmailNotVerifiedException
    ):
        logger.info(f"Authentication blocked: email unverified ({exc})")
        return format_error_response(
            code="EMAIL_NOT_VERIFIED",
            message=str(exc) or "Please verify your email address before logging in.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @app.exception_handler(InvalidVerificationTokenException)
    async def invalid_verification_token_exception_handler(
        _request: Request, exc: InvalidVerificationTokenException
    ):
        logger.info(f"Verification rejected: {exc}")
        return format_error_response(
            code="INVALID_VERIFICATION_TOKEN",
            message=str(exc) or "Invalid verification code or link.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(ExpiredVerificationTokenException)
    async def expired_verification_token_exception_handler(
        _request: Request, exc: ExpiredVerificationTokenException
    ):
        logger.info(f"Verification expired: {exc}")
        return format_error_response(
            code="EXPIRED_VERIFICATION_TOKEN",
            message=str(exc)
            or "Verification code has expired. Please request a new one.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(MaxVerificationAttemptsException)
    async def max_verification_attempts_exception_handler(
        _request: Request, exc: MaxVerificationAttemptsException
    ):
        logger.warning(f"Verification rate limit reached: {exc}")
        return format_error_response(
            code="MAX_VERIFICATION_ATTEMPTS",
            message=str(exc)
            or "Too many failed attempts. Please request a new verification code.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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
        response.delete_cookie(
            key=settings.ACCESS_TOKEN_COOKIE_NAME,
            path="/",
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
    async def token_budget_exceeded_handler(
        _request: Request, exc: TokenBudgetExceeded
    ):
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
