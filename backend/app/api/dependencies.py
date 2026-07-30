from typing import Any

import jwt
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.domain.interfaces import TokenProvider
from app.auth.infrastructure.crypto.password_hasher import Argon2PasswordHasher
from app.auth.infrastructure.crypto.token_provider import JWTTokenProvider
from app.auth.infrastructure.persistence.repositories.session_repository import (
    SQLAlchemySessionRepository,
)
from app.auth.infrastructure.persistence.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from app.auth.infrastructure.providers import (
    SQLAlchemyUnitOfWork,
    SystemTimeProvider,
    SystemUUIDGenerator,
)
from app.auth.services.auth_service import AuthService
from app.core.config import settings
from app.db.session import get_db
from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.infrastructure.persistence.repositories.document_repository import (
    SQLAlchemyDocumentRepository,
)
from app.documents.infrastructure.storage import LocalStorageProvider
from app.documents.infrastructure.tasks import (
    FastAPIBackgroundTasksQueue,
)
from app.documents.services.chunking import ChunkingService
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.document_service import DocumentService
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner

# Security header scheme helper
security_scheme = HTTPBearer(auto_error=False)


def get_token_provider() -> TokenProvider:
    return JWTTokenProvider()


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """
    Composition Root for Dependency Injection.
    Wires domain interfaces to concrete infrastructure implementations.
    """
    user_repo = SQLAlchemyUserRepository(db)
    session_repo = SQLAlchemySessionRepository(db)
    hasher = Argon2PasswordHasher()
    token_provider = JWTTokenProvider()
    time_provider = SystemTimeProvider()
    uuid_generator = SystemUUIDGenerator()
    uow = SQLAlchemyUnitOfWork(db)

    return AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        hasher=hasher,
        token_provider=token_provider,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        uow=uow,
    )


class AuthenticationGuard:
    def __init__(self, token_provider: TokenProvider | None = None) -> None:
        self._token_provider = token_provider or JWTTokenProvider()

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    ) -> dict[str, Any]:
        """
        Stateless authentication check. Signature verified in-memory.
        """
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        token = credentials.credentials
        try:
            claims = self._token_provider.decode_token(token)
            return claims
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
            import logging

            logging.getLogger(__name__).warning(f"JWT Verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            )


async def get_current_user_context(
    claims: dict[str, Any] = Depends(AuthenticationGuard()),
) -> dict[str, Any]:
    """
    CurrentUserProvider implementation.
    Extracts user details from claims context.
    """
    user_id = claims.get("sub")
    role = claims.get("role")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject identity",
        )
    return {"user_id": user_id, "role": role}


# --- Document Component Dependency Injection ---


def get_checksum_generator() -> SHA256ChecksumGenerator:
    return SHA256ChecksumGenerator()


def get_storage_provider() -> LocalStorageProvider:
    return LocalStorageProvider(upload_dir=settings.UPLOAD_DIR)


def get_extractor_factory() -> ExtractorFactory:
    return ExtractorFactory()


def get_text_cleaner() -> TextCleaner:
    return TextCleaner()


def get_metadata_extractor() -> MetadataExtractor:
    return MetadataExtractor()


def get_chunking_service() -> ChunkingService:
    return ChunkingService(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        min_chunk_size=settings.MIN_CHUNK_SIZE,
        strategy=settings.CHUNK_STRATEGY,
    )


def get_document_processing_service(
    db: Session = Depends(get_db),
) -> DocumentProcessingService:
    return DocumentProcessingService(
        document_repo=SQLAlchemyDocumentRepository(db),
        chunk_repo=SQLAlchemyChunkRepository(db),
        storage_provider=get_storage_provider(),
        extractor_factory=get_extractor_factory(),
        text_cleaner=get_text_cleaner(),
        metadata_extractor=get_metadata_extractor(),
        chunking_service=get_chunking_service(),
        uow=SQLAlchemyUnitOfWork(db),
        time_provider=SystemTimeProvider(),
    )


def get_document_service(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> DocumentService:
    task_queue = FastAPIBackgroundTasksQueue(background_tasks)
    return DocumentService(
        document_repo=SQLAlchemyDocumentRepository(db),
        storage_provider=get_storage_provider(),
        extractor_factory=get_extractor_factory(),
        checksum_generator=get_checksum_generator(),
        task_queue=task_queue,
        document_processing_service=get_document_processing_service(db),
        uow=SQLAlchemyUnitOfWork(db),
        uuid_generator=SystemUUIDGenerator(),
        time_provider=SystemTimeProvider(),
        max_upload_size=settings.MAX_UPLOAD_SIZE,
    )
