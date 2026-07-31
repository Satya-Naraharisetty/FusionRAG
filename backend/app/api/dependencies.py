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
from app.documents.domain.events import DocumentProcessingCompleted
from app.documents.domain.interfaces import (
    EmbeddingGenerator,
    EmbeddingRepository,
    VectorStore,
    ChunkRepository,
    SearchRanker,
)
from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher
from app.documents.infrastructure.extractors import ExtractorFactory
from app.documents.infrastructure.persistence.repositories.chunk_repository import (
    SQLAlchemyChunkRepository,
)
from app.documents.infrastructure.persistence.repositories.document_repository import (
    SQLAlchemyDocumentRepository,
)
from app.documents.infrastructure.persistence.repositories.embedding_repository import (
    SQLAlchemyEmbeddingRepository,
)
from app.documents.infrastructure.storage import LocalStorageProvider
from app.documents.infrastructure.tasks import (
    FastAPIBackgroundTasksQueue,
)
from app.documents.services.chunking import ChunkingService
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.document_service import DocumentService
from app.documents.services.embedding_service import EmbeddingService
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


def get_embedding_generator() -> EmbeddingGenerator:
    from app.documents.infrastructure.embedding_generator import (
        OpenAIEmbeddingGenerator,
    )

    return OpenAIEmbeddingGenerator(
        api_key=settings.OPENAI_API_KEY,
        model=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
    )


def get_vector_store(request: Request = None) -> VectorStore:
    from app.documents.infrastructure.persistence.vector_store import QdrantVectorStore

    if (
        request
        and hasattr(request, "app")
        and hasattr(request.app, "state")
        and hasattr(request.app.state, "qdrant")
    ):
        qdrant_client = request.app.state.qdrant
    else:
        from app.db.session import init_qdrant_client

        qdrant_client = init_qdrant_client(settings.QDRANT_HOST, settings.QDRANT_PORT)

    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=settings.VECTOR_COLLECTION_NAME,
        dimension=settings.EMBEDDING_DIMENSION,
    )


def get_embedding_repository(db: Session = Depends(get_db)) -> EmbeddingRepository:
    from app.documents.infrastructure.persistence.repositories.embedding_repository import (
        SQLAlchemyEmbeddingRepository,
    )

    return SQLAlchemyEmbeddingRepository(db)


def get_embedding_service(
    db: Session = Depends(get_db),
    generator: EmbeddingGenerator = Depends(get_embedding_generator),
    vector_store: VectorStore = Depends(get_vector_store),
) -> EmbeddingService:
    from app.documents.services.embedding_service import EmbeddingService

    return EmbeddingService(
        embedding_generator=generator,
        vector_store=vector_store,
        embedding_repo=SQLAlchemyEmbeddingRepository(db),
        chunk_repo=SQLAlchemyChunkRepository(db),
        document_repo=SQLAlchemyDocumentRepository(db),
        uow=SQLAlchemyUnitOfWork(db),
        time_provider=SystemTimeProvider(),
        uuid_generator=SystemUUIDGenerator(),
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        provider_name=settings.EMBEDDING_PROVIDER,
        model_name=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
        embedding_version=settings.EMBEDDING_VERSION,
    )


def get_document_processing_service(
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    request: Request = None,
) -> DocumentProcessingService:
    dispatcher = SimpleEventDispatcher()

    if request and hasattr(request, "background_tasks"):
        task_queue = FastAPIBackgroundTasksQueue(request.background_tasks)
    else:
        from app.documents.infrastructure.tasks import SyncTaskQueue

        task_queue = SyncTaskQueue()

    def handle_document_completed(event: DocumentProcessingCompleted) -> None:
        task_queue.enqueue(embedding_service.generate_embeddings, event.document_id)

    dispatcher.register(DocumentProcessingCompleted, handle_document_completed)

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
        event_dispatcher=dispatcher,
    )


def get_document_service(
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    processing_service: DocumentProcessingService = Depends(
        get_document_processing_service
    ),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> DocumentService:
    task_queue = FastAPIBackgroundTasksQueue(background_tasks)
    # Re-wire the request task queue into the dynamically resolved processing service
    if hasattr(processing_service, "_event_dispatcher"):

        def handle_document_completed(event: DocumentProcessingCompleted) -> None:
            task_queue.enqueue(embedding_service.generate_embeddings, event.document_id)

        # Clear and re-register to use the correct request background tasks queue
        processing_service._event_dispatcher._handlers[DocumentProcessingCompleted] = [
            handle_document_completed
        ]

    return DocumentService(
        document_repo=SQLAlchemyDocumentRepository(db),
        storage_provider=get_storage_provider(),
        extractor_factory=get_extractor_factory(),
        checksum_generator=get_checksum_generator(),
        task_queue=task_queue,
        document_processing_service=processing_service,
        embedding_service=embedding_service,
        uow=SQLAlchemyUnitOfWork(db),
        uuid_generator=SystemUUIDGenerator(),
        time_provider=SystemTimeProvider(),
        max_upload_size=settings.MAX_UPLOAD_SIZE,
    )


def get_chunk_repository(db: Session = Depends(get_db)) -> ChunkRepository:
    from app.documents.infrastructure.persistence.repositories.chunk_repository import (
        SQLAlchemyChunkRepository,
    )
    return SQLAlchemyChunkRepository(db)


def get_search_ranker() -> SearchRanker:
    from app.documents.services.ranking import SemanticSearchRanker
    return SemanticSearchRanker()


def get_retrieval_service(
    generator: EmbeddingGenerator = Depends(get_embedding_generator),
    vector_store: VectorStore = Depends(get_vector_store),
    chunk_repo: ChunkRepository = Depends(get_chunk_repository),
    ranker: SearchRanker = Depends(get_search_ranker),
) -> RetrievalService:
    from app.documents.services.retrieval_service import RetrievalService

    return RetrievalService(
        embedding_generator=generator,
        vector_store=vector_store,
        chunk_repo=chunk_repo,
        ranker=ranker,
        similarity_threshold=settings.SIMILARITY_THRESHOLD,
        search_timeout=settings.SEARCH_TIMEOUT,
    )
