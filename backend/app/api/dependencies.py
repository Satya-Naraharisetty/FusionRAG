import logging
from typing import Any

import jwt
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.interfaces import TokenProvider
from app.auth.infrastructure.crypto.password_hasher import Argon2PasswordHasher
from app.auth.infrastructure.crypto.token_provider import JWTTokenProvider
from app.auth.infrastructure.persistence.repositories.email_verification_repository import (
    SQLAlchemyEmailVerificationRepository,
)
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
from app.auth.services.oauth_service import OAuthService
from app.core.config import settings
from app.core.email.resend_service import get_resend_service
from app.core.queue.interfaces import DurableTaskQueue
from app.db.session import get_db
from app.documents.domain.events import DocumentProcessingCompleted
from app.documents.domain.interfaces import (
    ChunkRepository,
    EmbeddingGenerator,
    EmbeddingRepository,
    IndexCache,
    SearchRanker,
    SparseIndex,
    VectorStore,
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
from app.documents.services.chunking import ChunkingService
from app.documents.services.document_processing_service import DocumentProcessingService
from app.documents.services.document_service import DocumentService
from app.documents.services.embedding_service import EmbeddingService
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner

logger = logging.getLogger(__name__)

# Security header scheme helper
security_scheme = HTTPBearer(auto_error=False)


def get_token_provider() -> TokenProvider:
    return JWTTokenProvider()


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """
    Composition Root for Dependency Injection.
    Wires domain interfaces to concrete infrastructure implementations.
    """
    user_repo = SQLAlchemyUserRepository(db)
    session_repo = SQLAlchemySessionRepository(db)
    verification_repo = SQLAlchemyEmailVerificationRepository(db)
    hasher = Argon2PasswordHasher()
    token_provider = JWTTokenProvider()
    time_provider = SystemTimeProvider()
    uuid_generator = SystemUUIDGenerator()
    uow = SQLAlchemyUnitOfWork(db)
    email_service = get_resend_service()

    return AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        hasher=hasher,
        token_provider=token_provider,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        uow=uow,
        verification_repo=verification_repo,
        email_service=email_service,
    )


def get_oauth_service(db: AsyncSession = Depends(get_db)) -> OAuthService:
    """
    Composition root for OAuthService.
    """
    user_repo = SQLAlchemyUserRepository(db)
    time_provider = SystemTimeProvider()
    uuid_generator = SystemUUIDGenerator()
    uow = SQLAlchemyUnitOfWork(db)

    return OAuthService(
        user_repo=user_repo,
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
        credentials: HTTPAuthorizationCredentials | None = Depends(
            HTTPBearer(
                auto_error=False
            )  # auto_error=False: missing header falls through to cookie
        ),
    ) -> dict[str, Any]:
        """
        Stateless authentication check. Signature verified in-memory.
        Accepts the access token from the Authorization header (Bearer) or
        the HttpOnly access_token cookie — header takes priority.
        """
        # Try Authorization header first (API clients, SSE with explicit token)
        token: str | None = credentials.credentials if credentials else None

        # Fall back to HttpOnly cookie (browser clients)
        if not token:
            token = request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        try:
            claims = self._token_provider.decode_token(token)
            return claims
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
            logger.warning("JWT Verification failed: %s", e)
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


# --- Security & Rate Limiting ---


def _build_rate_limiter(
    request: Request,
    requests_per_minute: int,
    burst: int,
    window_seconds: float = 60.0,
) -> Any:
    """Create a Redis-backed RateLimiter (falling back to in-memory), honoring ENABLE_RATE_LIMITER."""
    from app.core.security.rate_limiter import RateLimiter
    from app.db.session import get_redis

    if not settings.ENABLE_RATE_LIMITER:
        return RateLimiter(
            redis_client=None,
            requests_per_minute=999999,
            burst=999999,
            window_seconds=window_seconds,
        )

    try:
        redis_client = get_redis(request)
    except Exception:
        redis_client = None

    return RateLimiter(
        redis_client=redis_client,
        requests_per_minute=requests_per_minute,
        burst=burst,
        window_seconds=window_seconds,
    )


def get_rate_limiter(request: Request) -> Any:
    return _build_rate_limiter(
        request,
        settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
        settings.RATE_LIMIT_BURST,
    )


def _resolve_rate_limit_identifier(request: Request) -> str:
    """
    Resolve the rate-limit key: the authenticated user id when present, the
    client IP otherwise. Decodes the Bearer token directly so it also works
    for endpoints whose auth guard has not run yet.
    """
    from app.core.context.request_context import current_request_context

    ctx = current_request_context.get()
    if ctx and ctx.user_id:
        return f"user:{ctx.user_id}"
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            claims = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            sub = claims.get("sub")
            if sub:
                return f"user:{sub}"
    except Exception:
        pass
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


async def check_rate_limit(
    request: Request,
    rate_limiter: Any = Depends(get_rate_limiter),
) -> None:
    identifier = _resolve_rate_limit_identifier(request)
    if await rate_limiter.is_rate_limited(identifier):
        retry_after = str(int(getattr(rate_limiter, "window_seconds", 60)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": retry_after},
        )


def get_account_delete_rate_limiter(request: Request) -> Any:
    """
    Strict per-user limiter for the password-gated DELETE /auth/account.

    Account deletion re-verifies the password, so a compromised access token
    must not permit unlimited guesses against that re-entry field.
    """
    return _build_rate_limiter(
        request,
        settings.ACCOUNT_DELETE_RATE_LIMIT_PER_MINUTE,
        burst=0,
    )


async def check_account_delete_rate_limit(
    request: Request,
    rate_limiter: Any = Depends(get_account_delete_rate_limiter),
) -> None:
    identifier = _resolve_rate_limit_identifier(request)
    if await rate_limiter.is_rate_limited(identifier):
        retry_after = str(int(getattr(rate_limiter, "window_seconds", 60)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": retry_after},
        )


def get_metrics_rate_limiter(request: Request) -> Any:
    """Rate limiter for /metrics endpoint to prevent scraping DoS."""
    return _build_rate_limiter(
        request,
        getattr(settings, "METRICS_RATE_LIMIT_PER_MINUTE", 30),
        burst=5,
        window_seconds=60.0,
    )


async def check_metrics_rate_limit(
    request: Request,
    rate_limiter: Any = Depends(get_metrics_rate_limiter),
) -> None:
    identifier = _resolve_rate_limit_identifier(request)
    if await rate_limiter.is_rate_limited(identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many metrics requests. Please try again later.",
            headers={"Retry-After": "60"},
        )


def get_login_failed_attempts_tracker(request: Request) -> Any:
    """
    Tracker for consecutive failed login attempts (5 wrong attempts -> 5-minute lockout).
    """
    from app.core.security.rate_limiter import LoginAttemptTracker
    from app.db.session import get_redis

    if not settings.ENABLE_RATE_LIMITER:
        return LoginAttemptTracker(
            redis_client=None,
            max_attempts=999999,
            window_seconds=float(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
        )

    try:
        redis_client = get_redis(request)
    except Exception:
        redis_client = None

    return LoginAttemptTracker(
        redis_client=redis_client,
        max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=float(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    )


# --- Document Component Dependency Injection ---


def get_checksum_generator() -> SHA256ChecksumGenerator:
    return SHA256ChecksumGenerator()


def get_storage_provider(db: AsyncSession | None = None) -> Any:
    from app.core.config import settings
    from app.documents.infrastructure.storage import (
        DatabaseStorageProvider,
        LocalStorageProvider,
    )

    provider_type = settings.STORAGE_PROVIDER.lower()
    if provider_type == "local":
        return LocalStorageProvider(upload_dir=settings.UPLOAD_DIR)
    else:
        if db is None:
            raise RuntimeError(
                "Database session is required when using the database storage provider."
            )
        return DatabaseStorageProvider(db)


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
        parent_chunk_size=settings.PARENT_CHUNK_SIZE,
        parent_chunk_overlap=settings.PARENT_CHUNK_OVERLAP,
        child_chunk_size=settings.CHILD_CHUNK_SIZE,
        child_chunk_overlap=settings.CHILD_CHUNK_OVERLAP,
        sentence_window_size=settings.SENTENCE_WINDOW_SIZE,
        enable_parent_child=settings.ENABLE_PARENT_CHILD_RAG,
        enable_sentence_window=settings.ENABLE_SENTENCE_WINDOW_RAG,
        enable_contextual=settings.ENABLE_CONTEXTUAL_RETRIEVAL,
    )


_embedding_generator_instance: EmbeddingGenerator | None = None


def get_embedding_generator(request: Request = None) -> EmbeddingGenerator:  # type: ignore[assignment]
    import sys

    main_mod = sys.modules.get("app.main")
    if (
        main_mod
        and hasattr(main_mod, "app")
        and hasattr(main_mod.app, "dependency_overrides")
        and get_embedding_generator in main_mod.app.dependency_overrides
    ):
        return main_mod.app.dependency_overrides[get_embedding_generator]()

    global _embedding_generator_instance

    from app.core.config import settings

    # Singleton: construct once per process (both API and background workers).
    if _embedding_generator_instance is None:
        from app.documents.infrastructure.embedding_generator import (
            JinaEmbeddingGenerator,
        )

        logger.info("Using JinaEmbeddingGenerator for dense embeddings")
        _embedding_generator_instance = JinaEmbeddingGenerator(
            api_key=settings.get_jina_api_key(),
            model=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    return _embedding_generator_instance


def get_vector_store(request: Request = None) -> VectorStore:  # type: ignore[assignment]  # FastAPI injects Request
    import sys

    main_mod = sys.modules.get("app.main")
    if (
        main_mod
        and hasattr(main_mod, "app")
        and hasattr(main_mod.app, "dependency_overrides")
        and get_vector_store in main_mod.app.dependency_overrides
    ):
        return main_mod.app.dependency_overrides[get_vector_store]()

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

        qdrant_client = init_qdrant_client(
            settings.QDRANT_HOST,
            settings.QDRANT_PORT,
            settings.QDRANT_API_KEY,
            settings.QDRANT_URL,
        )

    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=settings.VECTOR_COLLECTION_NAME,
        dimension=settings.EMBEDDING_DIMENSION,
    )


def get_embedding_repository(db: AsyncSession = Depends(get_db)) -> EmbeddingRepository:
    from app.documents.infrastructure.persistence.repositories.embedding_repository import (
        SQLAlchemyEmbeddingRepository,
    )

    return SQLAlchemyEmbeddingRepository(db)


def get_embedding_service(
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    request: Request = None,  # type: ignore[assignment]  # FastAPI injects Request
) -> DocumentProcessingService:
    # Resolved lazily (not as a Depends default) because get_index_cache is
    # defined later in this module — module-level defaults are evaluated at
    # import time, function bodies only when called.
    index_cache = get_index_cache()
    dispatcher = SimpleEventDispatcher()

    task_queue: Any
    if request and hasattr(request, "background_tasks"):
        from app.documents.infrastructure.tasks import FastAPIBackgroundTasksQueue

        task_queue = FastAPIBackgroundTasksQueue(request.background_tasks)
    else:
        from app.documents.infrastructure.tasks import SyncTaskQueue

        task_queue = SyncTaskQueue()

    def handle_document_completed(event: DocumentProcessingCompleted) -> None:
        from app.documents.infrastructure.persistence.repositories.document_element_repository import (
            SQLAlchemyDocumentElementRepository,
        )
        from app.documents.infrastructure.persistence.repositories.graph_repository import (
            SQLAlchemyGraphRepository,
        )
        from app.documents.services.document_enrichment_service import (
            DocumentEnrichmentService,
        )
        from app.documents.services.table_processor import TableProcessor

        task_queue.enqueue(embedding_service.generate_embeddings, event.document_id)
        enrichment_service = DocumentEnrichmentService(
            document_repo=SQLAlchemyDocumentRepository(db),
            element_repo=SQLAlchemyDocumentElementRepository(db),
            graph_repo=SQLAlchemyGraphRepository(db),
            table_processor=TableProcessor(),
            uow=SQLAlchemyUnitOfWork(db),
        )
        task_queue.enqueue(
            enrichment_service.enrich_document,
            event.document_id,
            event.user_id,
        )

    dispatcher.register(DocumentProcessingCompleted, handle_document_completed)

    return DocumentProcessingService(
        document_repo=SQLAlchemyDocumentRepository(db),
        chunk_repo=SQLAlchemyChunkRepository(db),
        storage_provider=get_storage_provider(db),
        extractor_factory=get_extractor_factory(),
        text_cleaner=get_text_cleaner(),
        metadata_extractor=get_metadata_extractor(),
        chunking_service=get_chunking_service(),
        uow=SQLAlchemyUnitOfWork(db),
        time_provider=SystemTimeProvider(),
        event_dispatcher=dispatcher,
        index_cache=index_cache,
    )


def get_malware_scanner() -> Any:
    from app.core.config import settings
    from app.core.security.malware import ClamAVScanner, StubMalwareScanner

    scanner_type = getattr(settings, "MALWARE_SCANNER_TYPE", "stub")
    clamav_host = getattr(settings, "CLAMAV_HOST", None)
    if scanner_type == "clamav" or (settings.is_production and clamav_host):
        return ClamAVScanner(
            host=clamav_host or "localhost",
            port=getattr(settings, "CLAMAV_PORT", 3310),
            timeout_seconds=getattr(settings, "CLAMAV_TIMEOUT_SECONDS", 10.0),
            fail_closed=getattr(settings, "MALWARE_SCAN_FAIL_CLOSED", True),
        )
    return StubMalwareScanner()


_index_cache_instance: Any = None


def get_index_cache():
    """
    Returns the single process-wide InMemoryIndexCache instance.

    Note: this deliberately does NOT use the lru_cache-on-nested-function idiom
    (each call to the outer function would create a fresh wrapper with a fresh
    cache, silently defeating the caching). A module-global singleton is the
    pattern used by get_cache / get_pricing_provider in this file.
    """
    global _index_cache_instance

    if _index_cache_instance is None:
        from app.documents.services.index_cache import InMemoryIndexCache

        _index_cache_instance = InMemoryIndexCache()
    return _index_cache_instance


_in_memory_task_queue_instance: Any = None


def get_durable_task_queue(
    request: Request = None,  # type: ignore[assignment]
) -> DurableTaskQueue:
    """
    Returns the configured DurableTaskQueue instance.
    In testing or when QUEUE_TYPE is in_memory, returns InMemoryDurableTaskQueue.
    In production/dev, returns RedisStreamTaskQueue.
    """
    global _in_memory_task_queue_instance
    if settings.is_testing or settings.QUEUE_TYPE == "in_memory":
        if _in_memory_task_queue_instance is None:
            from app.core.queue.in_memory import InMemoryDurableTaskQueue

            dispatcher = (
                getattr(request.app.state, "job_dispatcher", None)
                if request and hasattr(request, "app") and hasattr(request.app, "state")
                else None
            )
            _in_memory_task_queue_instance = InMemoryDurableTaskQueue(
                dispatcher=dispatcher,
                auto_dispatch=True,
            )
        return _in_memory_task_queue_instance

    if request and hasattr(request.app.state, "durable_task_queue"):
        return request.app.state.durable_task_queue

    from app.core.queue.redis_queue import RedisStreamTaskQueue

    redis_client = getattr(request.app.state, "redis", None) if request else None
    if redis_client is None:
        from app.db.session import init_redis_client

        redis_client = init_redis_client(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            url=settings.REDIS_URL,
        )
    return RedisStreamTaskQueue(
        redis_client=redis_client,
        stream_name=settings.QUEUE_STREAM_NAME,
        consumer_group=settings.QUEUE_CONSUMER_GROUP,
    )


def get_document_service(
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    processing_service: DocumentProcessingService = Depends(
        get_document_processing_service
    ),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    index_cache: IndexCache = Depends(get_index_cache),
    task_queue: DurableTaskQueue = Depends(get_durable_task_queue),
) -> DocumentService:
    return DocumentService(
        document_repo=SQLAlchemyDocumentRepository(db),
        storage_provider=get_storage_provider(db),
        extractor_factory=get_extractor_factory(),
        checksum_generator=get_checksum_generator(),
        task_queue=task_queue,
        document_processing_service=processing_service,
        embedding_service=embedding_service,
        uow=SQLAlchemyUnitOfWork(db),
        uuid_generator=SystemUUIDGenerator(),
        time_provider=SystemTimeProvider(),
        max_upload_size=settings.MAX_UPLOAD_SIZE,
        index_cache=index_cache,
        malware_scanner=get_malware_scanner(),
    )


def get_chunk_repository(db: AsyncSession = Depends(get_db)) -> ChunkRepository:
    from app.documents.infrastructure.persistence.repositories.chunk_repository import (
        SQLAlchemyChunkRepository,
    )

    return SQLAlchemyChunkRepository(db)


def get_document_repository(db: AsyncSession = Depends(get_db)) -> Any:
    from app.documents.infrastructure.persistence.repositories.document_repository import (
        SQLAlchemyDocumentRepository,
    )

    return SQLAlchemyDocumentRepository(db)


def get_search_ranker() -> SearchRanker:
    from app.documents.services.ranking import SemanticSearchRanker

    return SemanticSearchRanker()


_reranker_instance: Any = None


def get_reranker() -> Any:
    """
    Returns the process-wide Reranker instance.
    Constructs JinaReranker when provider is 'jina' or JINA_API_KEY is configured,
    or IdentityReranker when reranker is disabled or initialization fails.
    """
    global _reranker_instance

    from app.core.config import settings

    if not settings.ENABLE_RERANKER:
        from app.documents.services.reranker import IdentityReranker

        return IdentityReranker()

    if _reranker_instance is None:
        from app.documents.services.reranker import (
            IdentityReranker,
            JinaCrossEncoderReranker,
        )

        provider = (settings.RERANKER_PROVIDER or "").lower().strip()
        if provider == "jina" or settings.JINA_API_KEY:
            try:
                _reranker_instance = JinaCrossEncoderReranker(
                    api_key=settings.JINA_API_KEY,
                    model_name=settings.RERANKER_MODEL
                    or "jina-reranker-v2-base-multilingual",
                    concurrency_limit=settings.RERANKER_CONCURRENCY_LIMIT,
                )
            except Exception as e:
                logger.error(
                    f"Failed to instantiate JinaCrossEncoderReranker: {e}. Falling back to IdentityReranker."
                )
                return IdentityReranker()
        else:
            return IdentityReranker()

    return _reranker_instance


def get_retrieval_service(
    generator: EmbeddingGenerator = Depends(get_embedding_generator),
    vector_store: VectorStore = Depends(get_vector_store),
    chunk_repo: ChunkRepository = Depends(get_chunk_repository),
    db: AsyncSession = Depends(get_db),
    index_cache=Depends(get_index_cache),
    reranker=Depends(get_reranker),
) -> Any:
    from app.documents.services.dense_retriever import QdrantDenseRetriever
    from app.documents.services.fusion import ReciprocalRankFusionEngine
    from app.documents.services.mmr import DefaultMMRSelector
    from app.documents.services.query_classifier import DeterministicQueryClassifier
    from app.documents.services.query_decomposer import SafeQueryDecomposer
    from app.documents.services.query_expansion import SafeQueryExpander
    from app.documents.services.query_processor import DefaultQueryProcessor
    from app.documents.services.retrieval_service import RetrievalService
    from app.documents.services.sparse_index import InMemoryBM25Index
    from app.documents.services.sparse_retriever import BM25Retriever

    acronyms = {"rag": "retrieval augmented generation", "llm": "large language model"}
    typos = {"searc": "search", "retreival": "retrieval", "embeding": "embedding"}

    query_processor = DefaultQueryProcessor(acronyms=acronyms, typos=typos)

    dense_retriever = QdrantDenseRetriever(
        embedding_generator=generator,
        vector_store=vector_store,
        chunk_repo=chunk_repo,
        similarity_threshold=settings.SIMILARITY_THRESHOLD,
        search_timeout=settings.SEARCH_TIMEOUT,
    )

    sparse_index: SparseIndex
    if settings.SPARSE_RETRIEVER_TYPE == "postgres_fts":
        from app.documents.services.postgres_sparse_retriever import (
            PostgresSparseRetriever,
        )

        sparse_index = PostgresSparseRetriever(db=db, chunk_repo=chunk_repo)
    else:
        sparse_index = InMemoryBM25Index(
            chunk_repo=chunk_repo,
            index_cache=index_cache,
        )
    sparse_retriever = BM25Retriever(sparse_index=sparse_index)

    fusion_engine = ReciprocalRankFusionEngine(rrf_k=settings.RRF_K)
    mmr_selector = DefaultMMRSelector()

    return RetrievalService(
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion_engine=fusion_engine,
        mmr_selector=mmr_selector,
        reranker=reranker,
        chunk_repo=chunk_repo,
        index_cache=index_cache,
        enable_hybrid_search=settings.ENABLE_HYBRID_SEARCH,
        enable_mmr=settings.ENABLE_MMR,
        enable_reranker=settings.ENABLE_RERANKER,
        vector_top_k=settings.VECTOR_TOP_K,
        bm25_top_k=settings.BM25_TOP_K,
        mmr_lambda=settings.MMR_LAMBDA,
        rerank_top_k=settings.RERANK_TOP_K,
        enable_query_classification=settings.ENABLE_QUERY_CLASSIFICATION,
        enable_query_expansion=settings.ENABLE_QUERY_EXPANSION,
        enable_query_decomposition=settings.ENABLE_QUERY_DECOMPOSITION,
        enable_weighted_rrf=settings.ENABLE_WEIGHTED_RRF,
        dense_weight=settings.DENSE_WEIGHT,
        sparse_weight=settings.SPARSE_WEIGHT,
        max_total_retrieval_queries=settings.MAX_TOTAL_RETRIEVAL_QUERIES,
        max_retrieval_candidates=settings.MAX_RETRIEVAL_CANDIDATES,
        query_classifier=DeterministicQueryClassifier(),
        query_expander=SafeQueryExpander(
            timeout_ms=settings.QUERY_EXPANSION_TIMEOUT_MS,
            max_queries=settings.QUERY_EXPANSION_MAX_QUERIES,
        ),
        query_decomposer=SafeQueryDecomposer(
            timeout_ms=settings.QUERY_DECOMPOSITION_TIMEOUT_MS,
            max_subtasks=settings.MAX_QUERY_SUBTASKS,
        ),
    )


def get_llm_provider(request: Request = None):  # type: ignore[assignment]
    import sys

    main_mod = sys.modules.get("app.main")
    if (
        main_mod
        and hasattr(main_mod, "app")
        and hasattr(main_mod.app, "dependency_overrides")
        and get_llm_provider in main_mod.app.dependency_overrides
    ):
        return main_mod.app.dependency_overrides[get_llm_provider]()

    from app.chat.infrastructure.gemini_provider import GeminiProvider

    return GeminiProvider(api_key=settings.get_gemini_llm_api_key())


def get_planner_llm_provider(request: Request = None):  # type: ignore[assignment]
    import sys

    main_mod = sys.modules.get("app.main")
    if (
        main_mod
        and hasattr(main_mod, "app")
        and hasattr(main_mod.app, "dependency_overrides")
        and get_planner_llm_provider in main_mod.app.dependency_overrides
    ):
        return main_mod.app.dependency_overrides[get_planner_llm_provider]()

    from app.chat.infrastructure.gemini_provider import GeminiProvider

    return GeminiProvider(api_key=settings.get_gemini_planner_api_key())


def get_intent_classifier(request: Request = None) -> Any:  # type: ignore[assignment]
    if not settings.ENABLE_INTENT_GUARDRAILS:
        return None

    import sys

    main_mod = sys.modules.get("app.main")
    if (
        main_mod
        and hasattr(main_mod, "app")
        and hasattr(main_mod.app, "dependency_overrides")
        and get_intent_classifier in main_mod.app.dependency_overrides
    ):
        return main_mod.app.dependency_overrides[get_intent_classifier]()

    import google.generativeai as genai

    from app.core.security.intent_classifier import IntentClassifier

    genai.configure(api_key=settings.get_gemini_llm_api_key())
    client = genai.GenerativeModel(model_name="gemini-3.5-flash-lite")
    return IntentClassifier(gemini_client=client)


def get_hyde_executor(
    generator: EmbeddingGenerator = Depends(get_embedding_generator),
    retrieval_service: Any = Depends(get_retrieval_service),
    llm_provider: Any = Depends(get_llm_provider),
) -> Any:
    from app.chat.services.llm_generation_service import LLMGenerationService
    from app.documents.services.hyde import (
        DeterministicHyDEGenerator,
        LLMHyDEGenerator,
        SafeHyDEExecutor,
    )

    dense_retriever = getattr(retrieval_service, "_dense_retriever", None)
    if dense_retriever is None:
        return None

    hyde_gen: Any
    if getattr(settings, "HYDE_GENERATOR_TYPE", "deterministic") == "llm":
        llm_gen = LLMGenerationService(llm_provider)
        hyde_gen = LLMHyDEGenerator(
            llm_generation_service=llm_gen,
            model=settings.GEMINI_CHAT_MODEL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.HYDE_MAX_TOKENS,
            timeout_ms=settings.HYDE_TIMEOUT_MS,
            max_retries=settings.HYDE_MAX_RETRIES,
            fallback_generator=DeterministicHyDEGenerator(),
        )
    else:
        hyde_gen = DeterministicHyDEGenerator()

    return SafeHyDEExecutor(
        hyde_generator=hyde_gen,
        embedding_generator=generator,
        dense_retriever=dense_retriever,
        timeout_ms=settings.HYDE_TIMEOUT_MS,
    )


def get_adaptive_rag_orchestrator(
    retrieval_service: Any = Depends(get_retrieval_service),
    hyde_executor: Any = Depends(get_hyde_executor),
    chunk_repo: Any = Depends(get_chunk_repository),
) -> Any:
    from app.documents.services.query_classifier import DeterministicQueryClassifier
    from app.documents.services.query_decomposer import DeterministicQueryDecomposer
    from app.rag.orchestration.evidence_evaluator import EvidenceSufficiencyEvaluator
    from app.rag.orchestration.master import AdaptiveRAGOrchestrator
    from app.rag.orchestration.replanner import Replanner
    from app.rag.orchestration.strategy_router import RetrievalStrategyRouter
    from app.rag.orchestration.telemetry import OrchestrationTelemetry

    query_classifier = DeterministicQueryClassifier()
    return AdaptiveRAGOrchestrator(
        retrieval_service=retrieval_service,
        strategy_router=RetrievalStrategyRouter(query_classifier),
        evidence_evaluator=EvidenceSufficiencyEvaluator(
            min_relevance_threshold=settings.SIMILARITY_THRESHOLD,
        ),
        replanner=Replanner(),
        query_classifier=query_classifier,
        query_decomposer=DeterministicQueryDecomposer(),
        hyde_executor=hyde_executor,
        telemetry=OrchestrationTelemetry(),
        chunk_repo=chunk_repo,
        max_iterations=settings.MAX_AGENT_ITERATIONS,
        max_tasks=settings.MAX_AGENT_TASKS,
        max_retrieval_calls=settings.MAX_AGENT_RETRIEVAL_CALLS,
        max_replans=settings.MAX_AGENT_REPLANS,
        total_timeout_ms=settings.AGENT_TOTAL_TIMEOUT_MS,
    )


# --- Chat & LLM Orchestration Component Dependency Injection ---


def get_token_estimator():
    from app.chat.services.token_estimator import CharacterTokenEstimator

    return CharacterTokenEstimator()


# Global PromptBuilder instance cached system prompt at startup
_prompt_builder_instance = None


def get_prompt_builder():
    global _prompt_builder_instance
    if _prompt_builder_instance is None:
        from app.chat.services.prompt_builder import PromptBuilder

        _prompt_builder_instance = PromptBuilder(
            system_prompt_path=settings.SYSTEM_PROMPT_PATH
        )
    return _prompt_builder_instance


def get_context_selector(
    token_estimator=Depends(get_token_estimator),
    chunk_repo: ChunkRepository = Depends(get_chunk_repository),
) -> Any:
    from app.documents.services.context_selector import ContextSelector

    return ContextSelector(
        token_estimator=token_estimator,
        max_context_tokens=settings.CONTEXT_MAX_TOKENS,
        max_chunks=settings.CONTEXT_MAX_CHUNKS,
        min_chunk_score=settings.CONTEXT_MIN_CHUNK_SCORE,
        score_source=settings.CONTEXT_SCORE_SOURCE,
        ordering_strategy=settings.CONTEXT_ORDERING_STRATEGY,
        enable_neighbor_chunks=settings.ENABLE_NEIGHBOR_CHUNKS,
        neighbor_window=settings.NEIGHBOR_CHUNK_WINDOW,
        enable_parent_child=settings.ENABLE_PARENT_CHILD_RAG,
        enable_sentence_window=settings.ENABLE_SENTENCE_WINDOW_RAG,
        chunk_repo=chunk_repo,
    )


def get_context_builder(
    token_estimator=Depends(get_token_estimator),
    context_selector=Depends(get_context_selector),
) -> Any:
    from app.chat.services.context_builder import ContextBuilder

    return ContextBuilder(
        token_estimator=token_estimator,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
        context_selector=context_selector,
        enable_context_selection=settings.ENABLE_CONTEXT_SELECTION,
    )


def get_conversation_repository(db: AsyncSession = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import (
        SQLAlchemyConversationRepository,
    )

    return SQLAlchemyConversationRepository(db)


def get_message_repository(db: AsyncSession = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import (
        SQLAlchemyMessageRepository,
    )

    return SQLAlchemyMessageRepository(db)


def get_summary_repository(db: AsyncSession = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import (
        SQLAlchemySummaryRepository,
    )

    return SQLAlchemySummaryRepository(db)


def get_conversation_access_service(
    conversation_repo=Depends(get_conversation_repository),
) -> Any:
    from app.chat.services.access_service import ConversationAccessService

    return ConversationAccessService(conversation_repo)


def get_conversation_memory(
    message_repo=Depends(get_message_repository),
    summary_repo=Depends(get_summary_repository),
) -> Any:
    from app.chat.services.rolling_memory import RollingConversationMemory

    return RollingConversationMemory(
        message_repo=message_repo,
        summary_repo=summary_repo,
        max_messages=settings.MAX_MESSAGES_PER_CONTEXT,
    )


def get_history_rewrite_cache(request: Request = None) -> Any:  # type: ignore[assignment]  # FastAPI injects Request
    from app.chat.infrastructure.cache import MemoryRewriteCache, RedisRewriteCache

    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    if redis_client:
        return RedisRewriteCache(redis_client)
    return MemoryRewriteCache()


def get_history_rewriter(
    llm_provider=Depends(get_llm_provider),
    cache=Depends(get_history_rewrite_cache),
) -> Any:
    from app.chat.services.history_rewriter import LLMHistoryRewriter

    model = settings.GEMINI_CHAT_MODEL
    return LLMHistoryRewriter(
        llm_provider, model=model, cache=cache, cache_ttl_seconds=3600
    )


def get_conversation_title_generator(
    llm_provider=Depends(get_llm_provider),
) -> Any:
    from app.chat.services.title_generator import LLMConversationTitleGenerator

    model = settings.GEMINI_CHAT_MODEL
    return LLMConversationTitleGenerator(llm_provider, model=model)


def get_conversation_context_builder() -> Any:
    from app.chat.services.conversation_context_builder import (
        ConversationContextBuilder,
    )

    return ConversationContextBuilder()


# Global SimpleEventDispatcher instances cache
_dispatcher_instance = None


async def run_background_summarization(
    conversation_id: Any,
    message_id: Any,
    db_session_factory: Any,
    llm_provider_instance: Any,
) -> None:
    import logging

    logger = logging.getLogger(__name__)
    async with db_session_factory() as db:
        try:
            from app.chat.infrastructure.persistence.repositories import (
                SQLAlchemyMessageRepository,
                SQLAlchemySummaryRepository,
            )
            from app.chat.services.conversation_summarizer import (
                LLMConversationSummarizer,
            )

            message_repo = SQLAlchemyMessageRepository(db)
            summary_repo = SQLAlchemySummaryRepository(db)

            count = await message_repo.count_messages(conversation_id)
            if count >= settings.SUMMARY_TRIGGER_MESSAGES:
                model = settings.GEMINI_CHAT_MODEL
                summarizer = LLMConversationSummarizer(
                    llm_provider=llm_provider_instance,
                    summary_repo=summary_repo,
                    message_repo=message_repo,
                    model=model,
                    summary_max_tokens=settings.SUMMARY_MAX_TOKENS,
                )

                # Fetch all messages in chronological order
                messages = await message_repo.get_recent_messages(
                    conversation_id, limit=1000
                )
                up_to_idx = count - settings.MAX_MESSAGES_PER_CONTEXT - 1
                if up_to_idx >= 0:
                    up_to_msg = messages[up_to_idx]
                    await summarizer.summarize(conversation_id, up_to_msg.id)
                    await db.commit()
        except Exception as e:
            logger.exception(f"Error during background summarization task: {e}")


def get_event_dispatcher(
    request: Request = None,  # type: ignore[assignment]  # FastAPI injects Request
    llm_provider=Depends(get_llm_provider),
) -> Any:
    global _dispatcher_instance
    if _dispatcher_instance is None:
        import asyncio

        from app.chat.domain.events import ConversationMessageCreated
        from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher

        _dispatcher_instance = SimpleEventDispatcher()

        def handle_message_added(event: ConversationMessageCreated) -> None:
            durable_queue = get_durable_task_queue(request)

            async def _enqueue_summary() -> None:
                try:
                    await durable_queue.enqueue(
                        task_type="SUMMARIZE_CONVERSATION",
                        payload={
                            "conversation_id": str(event.conversation_id),
                            "message_id": str(event.message_id),
                        },
                        max_attempts=3,
                    )
                except Exception as ex:
                    logger.error(f"Failed to enqueue SUMMARIZE_CONVERSATION: {ex}")

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_enqueue_summary())
            except RuntimeError:
                asyncio.run(_enqueue_summary())

        _dispatcher_instance.register(ConversationMessageCreated, handle_message_added)

    return _dispatcher_instance


def get_conversation_manager(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    conversation_repo=Depends(get_conversation_repository),
    message_repo=Depends(get_message_repository),
    summary_repo=Depends(get_summary_repository),
    access_service=Depends(get_conversation_access_service),
    memory=Depends(get_conversation_memory),
    rewriter=Depends(get_history_rewriter),
    title_generator=Depends(get_conversation_title_generator),
    event_dispatcher=Depends(get_event_dispatcher),
    document_service=Depends(get_document_service),
) -> Any:
    from app.chat.services.conversation_manager import ConversationManager

    return ConversationManager(
        conversation_repo=conversation_repo,
        message_repo=message_repo,
        summary_repo=summary_repo,
        access_service=access_service,
        memory=memory,
        rewriter=rewriter,
        title_generator=title_generator,
        event_dispatcher=event_dispatcher,
        document_service=document_service,
        db=db,
        background_tasks=background_tasks,
    )


def get_answer_generation_service(
    retrieval_service=Depends(get_retrieval_service),
    prompt_builder=Depends(get_prompt_builder),
    llm_provider=Depends(get_llm_provider),
    token_estimator=Depends(get_token_estimator),
    conversation_manager=Depends(get_conversation_manager),
    conversation_context_builder=Depends(get_conversation_context_builder),
) -> Any:
    from app.chat.services.answer_generation_service import AnswerGenerationService

    model = settings.GEMINI_CHAT_MODEL
    return AnswerGenerationService(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
        token_estimator=token_estimator,
        conversation_manager=conversation_manager,
        context_builder=conversation_context_builder,
        model=model,
        temperature=settings.TEMPERATURE,
        max_response_tokens=settings.MAX_RESPONSE_TOKENS,
        system_prompt_tokens_limit=settings.SYSTEM_PROMPT_TOKENS,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
        reserved_completion_tokens=settings.RESERVED_COMPLETION_TOKENS,
        max_memory_tokens=settings.MAX_MEMORY_TOKENS,
        enable_conversation_memory=settings.ENABLE_CONVERSATION_MEMORY,
    )


def get_tool_registry(retrieval_service=Depends(get_retrieval_service)) -> Any:
    from app.chat.services.tool_registry import ToolRegistry
    from app.chat.services.tools.base import Tool
    from app.chat.services.tools.calculator import CalculatorTool
    from app.chat.services.tools.chunk_retrieval import RetrieveChunkTool
    from app.chat.services.tools.citation_lookup import CitationLookupTool
    from app.chat.services.tools.datetime import DateTimeTool
    from app.chat.services.tools.document_retrieval import RetrieveDocumentTool
    from app.chat.services.tools.semantic_search import SearchKnowledgeTool
    from app.chat.services.tools.web_search import WebSearchTool

    tools: list[Tool] = [
        SearchKnowledgeTool(retrieval_service),
        RetrieveDocumentTool(),
        RetrieveChunkTool(),
        CitationLookupTool(),
        CalculatorTool(),
        DateTimeTool(),
        WebSearchTool(),
    ]
    registry = ToolRegistry(tools)
    # Register aliases
    registry.register(tools[0], aliases=["semantic_search", "document_search"])
    registry.register(tools[6], aliases=["live_search", "search_web"])
    return registry


def get_tool_discovery_service(registry=Depends(get_tool_registry)) -> Any:
    from app.chat.services.tool_discovery import ToolDiscoveryService

    return ToolDiscoveryService(registry)


def get_tool_executor() -> Any:
    from app.chat.services.tool_executor import ToolExecutor

    return ToolExecutor(
        timeout=settings.TOOL_EXECUTION_TIMEOUT,
        result_size_limit=settings.TOOL_RESULT_SIZE_LIMIT,
        auto_retry_count=settings.TOOL_AUTO_RETRY_COUNT,
    )


def get_agent_executor(
    llm_provider=Depends(get_llm_provider),
    registry=Depends(get_tool_registry),
    executor=Depends(get_tool_executor),
    conversation_manager=Depends(get_conversation_manager),
    token_estimator=Depends(get_token_estimator),
) -> Any:
    from app.chat.services.agent_executor import AgentExecutor

    return AgentExecutor(
        llm_provider=llm_provider,
        tool_registry=registry,
        tool_executor=executor,
        conversation_manager=conversation_manager,
        token_estimator=token_estimator,
        max_iterations=settings.MAX_TOOL_ITERATIONS,
        max_tools_per_request=settings.MAX_TOOLS_PER_REQUEST,
    )


def get_research_agent(
    retrieval_service=Depends(get_retrieval_service),
    llm_provider=Depends(get_planner_llm_provider),
) -> Any:
    from app.chat.services.multi_agent.research_agent import ResearchAgent

    return ResearchAgent(retrieval_service=retrieval_service, llm_provider=llm_provider)


def get_document_agent(
    document_repo=Depends(get_document_repository),
    chunk_repo=Depends(get_chunk_repository),
) -> Any:
    from app.chat.services.multi_agent.document_agent import DocumentAgent

    return DocumentAgent(document_repo=document_repo, chunk_repo=chunk_repo)


def get_analysis_agent() -> Any:
    from app.chat.services.multi_agent.analysis_agent import AnalysisAgent

    return AnalysisAgent()


def get_web_search_service() -> Any:
    from app.chat.services.web_search_service import WebSearchService

    return WebSearchService()


def get_web_search_agent(
    web_search_service=Depends(get_web_search_service),
) -> Any:
    from app.chat.services.multi_agent.web_search_agent import WebSearchAgent

    return WebSearchAgent(web_search_service=web_search_service)


_capability_registry_instance: Any = None


def get_capability_registry() -> Any:
    global _capability_registry_instance
    if _capability_registry_instance is None:
        from app.chat.services.multi_agent.capability_registry import (
            create_default_capability_registry,
        )

        _capability_registry_instance = create_default_capability_registry()
    return _capability_registry_instance


# Global singleton telemetry sink instance
_telemetry_sink_instance: Any | None = None


def get_telemetry_sink() -> Any:
    global _telemetry_sink_instance
    if _telemetry_sink_instance is None:
        from app.chat.services.multi_agent.observability import InMemoryTelemetrySink

        _telemetry_sink_instance = InMemoryTelemetrySink()
    return _telemetry_sink_instance


def get_agent_observability_service(
    sink=Depends(get_telemetry_sink),
) -> Any:
    from app.chat.services.multi_agent.observability import AgentObservabilityService

    return AgentObservabilityService(
        sink=sink,
        enabled=settings.AGENT_OBSERVABILITY_ENABLED,
        max_events=settings.AGENT_TRACE_MAX_EVENTS,
        max_tasks=settings.AGENT_TRACE_MAX_TASKS,
        max_str_len=settings.AGENT_MAX_TELEMETRY_STRING_LEN,
        max_keys=settings.AGENT_MAX_TELEMETRY_METADATA_KEYS,
    )


def get_task_router(
    registry=Depends(get_capability_registry),
    llm_provider=Depends(get_planner_llm_provider),
    observability=Depends(get_agent_observability_service),
) -> Any:
    from app.chat.services.multi_agent.task_router import TaskRouter

    return TaskRouter(
        registry=registry,
        llm_provider=llm_provider,
        enable_llm_router=settings.ENABLE_LLM_CAPABILITY_ROUTER,
        observability=observability,
        max_cost_units=settings.MAX_ESTIMATED_AGENT_COST_UNITS,
        max_latency_ms=settings.MAX_ESTIMATED_LATENCY_MS,
    )


def get_document_element_repository(
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.documents.infrastructure.persistence.repositories.document_element_repository import (
        SQLAlchemyDocumentElementRepository,
    )

    return SQLAlchemyDocumentElementRepository(db)


def get_graph_repository(
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.documents.infrastructure.persistence.repositories.graph_repository import (
        SQLAlchemyGraphRepository,
    )

    return SQLAlchemyGraphRepository(db)


def get_graph_retriever(
    graph_repo=Depends(get_graph_repository),
) -> Any:
    from app.documents.services.graph_retriever import PostgresGraphRetriever

    return PostgresGraphRetriever(graph_repository=graph_repo)


def get_table_processor() -> Any:
    from app.documents.services.table_processor import TableProcessor

    return TableProcessor()


def get_vision_processor() -> Any:
    from app.documents.services.vision_processor import VisionProcessor

    return VisionProcessor()


def get_table_agent(
    table_processor=Depends(get_table_processor),
    element_repo=Depends(get_document_element_repository),
) -> Any:
    from app.chat.services.multi_agent.table_agent import TableAgent

    return TableAgent(table_processor=table_processor, element_repo=element_repo)


def get_vision_agent(
    vision_processor=Depends(get_vision_processor),
    element_repo=Depends(get_document_element_repository),
) -> Any:
    from app.chat.services.multi_agent.vision_agent import VisionAgent

    return VisionAgent(vision_processor=vision_processor, element_repo=element_repo)


def get_graph_agent(
    graph_retriever=Depends(get_graph_retriever),
) -> Any:
    from app.chat.services.multi_agent.graph_agent import GraphAgent

    return GraphAgent(graph_retriever=graph_retriever)


def get_agent_execution_engine(
    research_agent=Depends(get_research_agent),
    document_agent=Depends(get_document_agent),
    analysis_agent=Depends(get_analysis_agent),
    web_search_agent=Depends(get_web_search_agent),
    table_agent=Depends(get_table_agent),
    vision_agent=Depends(get_vision_agent),
    graph_agent=Depends(get_graph_agent),
    task_router=Depends(get_task_router),
    capability_registry=Depends(get_capability_registry),
    observability=Depends(get_agent_observability_service),
) -> Any:
    from app.chat.services.multi_agent.execution_engine import AgentExecutionEngine

    return AgentExecutionEngine(
        specialist_agents=[
            research_agent,
            document_agent,
            analysis_agent,
            web_search_agent,
            table_agent,
            vision_agent,
            graph_agent,
        ],
        task_router=task_router,
        capability_registry=capability_registry,
        observability=observability,
        max_specialist_tasks=settings.MAX_SPECIALIST_TASKS,
        max_total_calls=settings.MAX_TOTAL_AGENT_CALLS,
        task_timeout=settings.MULTI_AGENT_TASK_TIMEOUT,
        max_cost_units=settings.MAX_ESTIMATED_AGENT_COST_UNITS,
        max_latency_ms=settings.MAX_ESTIMATED_LATENCY_MS,
    )


def get_synthesis_agent(
    llm_provider=Depends(get_llm_provider),
) -> Any:
    from app.chat.services.multi_agent.synthesis_agent import SynthesisAgent

    return SynthesisAgent(llm_provider)


def get_master_agent(
    llm_provider=Depends(get_planner_llm_provider),
    execution_engine=Depends(get_agent_execution_engine),
    synthesis_agent=Depends(get_synthesis_agent),
    observability=Depends(get_agent_observability_service),
) -> Any:
    from app.chat.services.multi_agent.master_agent import MasterAgent

    return MasterAgent(
        llm_provider=llm_provider,
        execution_engine=execution_engine,
        synthesis_agent=synthesis_agent,
        observability=observability,
        max_plan_iterations=settings.MAX_PLAN_ITERATIONS,
        max_total_calls=settings.MAX_TOTAL_AGENT_CALLS,
    )


def get_chat_orchestrator(
    retrieval_service=Depends(get_retrieval_service),
    prompt_builder=Depends(get_prompt_builder),
    llm_provider=Depends(get_llm_provider),
    token_estimator=Depends(get_token_estimator),
    conversation_manager=Depends(get_conversation_manager),
    conversation_context_builder=Depends(get_conversation_context_builder),
    agent_executor=Depends(get_agent_executor),
    master_agent=Depends(get_master_agent),
    adaptive_rag_orchestrator=Depends(get_adaptive_rag_orchestrator),
) -> Any:
    from app.chat.services.chat_orchestrator import ChatOrchestrator
    from app.chat.services.llm_generation_service import LLMGenerationService

    llm_gen = LLMGenerationService(llm_provider)
    model = settings.GEMINI_CHAT_MODEL
    return ChatOrchestrator(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_generation_service=llm_gen,
        token_estimator=token_estimator,
        conversation_manager=conversation_manager,
        context_builder=conversation_context_builder,
        agent_executor=agent_executor,
        master_agent=master_agent,
        model=model,
        temperature=settings.TEMPERATURE,
        max_response_tokens=settings.MAX_RESPONSE_TOKENS,
        system_prompt_tokens_limit=settings.SYSTEM_PROMPT_TOKENS,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
        reserved_completion_tokens=settings.RESERVED_COMPLETION_TOKENS,
        max_memory_tokens=settings.MAX_MEMORY_TOKENS,
        enable_conversation_memory=settings.ENABLE_CONVERSATION_MEMORY,
        enable_tool_calling=settings.ENABLE_TOOL_CALLING,
        enable_multi_agent=settings.ENABLE_MULTI_AGENT,
        adaptive_rag_orchestrator=adaptive_rag_orchestrator,
        enable_adaptive_rag=settings.ENABLE_ADAPTIVE_RAG,
    )


# --- Evaluation Component Dependency Injection ---


def get_dataset_loader():
    from app.evaluation.datasets.dataset_loader import DatasetLoader

    return DatasetLoader()


def get_ragas_provider():
    from app.evaluation.runners.ragas_provider import RagasProvider

    return RagasProvider()


def get_deepeval_provider():
    from app.evaluation.runners.deepeval_provider import DeepEvalProvider

    return DeepEvalProvider()


def get_retrieval_evaluator(
    retrieval_service=Depends(get_retrieval_service),
):
    from app.evaluation.services.retrieval_evaluator import RetrievalEvaluator

    return RetrievalEvaluator(retrieval_service)


def get_agent_evaluator():
    from app.evaluation.services.agent_evaluator import AgentEvaluator

    return AgentEvaluator()


def get_tool_evaluator():
    from app.evaluation.services.tool_evaluator import ToolEvaluator

    return ToolEvaluator()


def get_citation_evaluator() -> Any:
    from app.evaluation.services.citation_evaluator import CitationEvaluator

    return CitationEvaluator()


def get_conversation_evaluator():
    from app.evaluation.services.conversation_evaluator import ConversationEvaluator

    return ConversationEvaluator()


def get_evaluation_runner(
    retrieval_evaluator=Depends(get_retrieval_evaluator),
    agent_evaluator=Depends(get_agent_evaluator),
    tool_evaluator=Depends(get_tool_evaluator),
    conversation_evaluator=Depends(get_conversation_evaluator),
    citation_evaluator=Depends(get_citation_evaluator),
    ragas_provider=Depends(get_ragas_provider),
    deepeval_provider=Depends(get_deepeval_provider),
):
    from app.evaluation.runners.evaluation_runner import EvaluationRunner

    return EvaluationRunner(
        retrieval_evaluator=retrieval_evaluator,
        agent_evaluator=agent_evaluator,
        tool_evaluator=tool_evaluator,
        conversation_evaluator=conversation_evaluator,
        citation_evaluator=citation_evaluator,
        ragas_provider=ragas_provider,
        deepeval_provider=deepeval_provider,
    )


def get_benchmark_runner(evaluation_runner=Depends(get_evaluation_runner)):
    from app.evaluation.runners.benchmark_runner import BenchmarkRunner

    return BenchmarkRunner(evaluation_runner=evaluation_runner)


def get_regression_runner():
    from app.evaluation.runners.regression_runner import RegressionRunner

    return RegressionRunner()


def get_report_generator():
    from app.evaluation.reports.report_generator import ReportGenerator

    return ReportGenerator(output_dir=settings.EVALUATION_RESULTS_DIR)


# --- Production Backend Layer Dependency Providers ---

_cache_instance: Any = None


def get_cache(request: Request = None) -> Any:  # type: ignore[assignment]  # FastAPI injects Request
    global _cache_instance
    if _cache_instance is None:
        from app.core.cache.memory_cache import InMemoryCache
        from app.core.cache.multi_tier import MultiTierCache
        from app.core.cache.redis_cache import RedisCache

        redis_client = None
        if request:
            try:
                redis_client = getattr(request.app.state, "redis", None)
            except Exception:
                pass

        l1 = InMemoryCache()
        if redis_client:
            l2 = RedisCache(redis_client)
            _cache_instance = MultiTierCache(l1, l2)
        else:
            _cache_instance = l1
    return _cache_instance


def get_distributed_lock(request: Request = None) -> Any:  # type: ignore[assignment]  # FastAPI injects Request
    from app.core.cache.lock import InMemoryDistributedLock, RedisDistributedLock

    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    if redis_client:
        return RedisDistributedLock(redis_client)
    return InMemoryDistributedLock()


def get_idempotency_manager(request: Request = None) -> Any:  # type: ignore[assignment]  # FastAPI injects Request
    from app.core.security.idempotency import IdempotencyManager

    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    if redis_client:
        return IdempotencyManager(redis_client)
    return None


def get_resource_quota_service(
    db: AsyncSession = Depends(get_db),
    request: Request = None,  # type: ignore[assignment]  # FastAPI injects Request
) -> Any:
    from app.core.security.quotas import ResourceQuotaService

    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    return ResourceQuotaService(db, redis_client)


_pricing_provider = None


def get_pricing_provider() -> Any:
    global _pricing_provider
    if _pricing_provider is None:
        import os

        from app.core.cost.pricing_provider import YAMLPricingProvider

        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "core", "cost", "pricing.yaml"
        )
        _pricing_provider = YAMLPricingProvider(yaml_path)
    return _pricing_provider


_feature_flag_service = None


def get_feature_flag_service() -> Any:
    global _feature_flag_service
    if _feature_flag_service is None:
        from app.core.feature_flags.flags import (
            FeatureFlagService,
            SettingsFeatureFlagProvider,
        )

        provider = SettingsFeatureFlagProvider()
        _feature_flag_service = FeatureFlagService(provider)
    return _feature_flag_service


_event_bus_instance: Any = None


def get_event_bus(request: Request = None) -> Any:  # type: ignore[assignment]  # FastAPI injects Request
    global _event_bus_instance
    if _event_bus_instance is None:
        from app.core.events.redis_bus import RedisEventBus

        redis_client = None
        if request:
            try:
                redis_client = getattr(request.app.state, "redis", None)
            except Exception:
                pass
        if redis_client:
            _event_bus_instance = RedisEventBus(redis_client)
        else:
            # Fallback to local dispatch placeholder
            class InProcessEventBus:
                async def publish(self, event):
                    pass

                async def subscribe(self, event_type, handler):
                    pass

            _event_bus_instance = InProcessEventBus()
    return _event_bus_instance
