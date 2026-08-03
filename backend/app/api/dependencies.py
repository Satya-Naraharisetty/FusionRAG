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


def get_index_cache():
    from functools import lru_cache
    from app.documents.services.index_cache import InMemoryIndexCache

    @lru_cache
    def _get_cache():
        return InMemoryIndexCache()
    return _get_cache()


def get_retrieval_service(
    generator: EmbeddingGenerator = Depends(get_embedding_generator),
    vector_store: VectorStore = Depends(get_vector_store),
    chunk_repo: ChunkRepository = Depends(get_chunk_repository),
    index_cache=Depends(get_index_cache),
) -> "RetrievalService":
    from app.documents.services.retrieval_service import RetrievalService
    from app.documents.services.query_processor import DefaultQueryProcessor
    from app.documents.services.dense_retriever import QdrantDenseRetriever
    from app.documents.services.sparse_index import InMemoryBM25Index
    from app.documents.services.sparse_retriever import BM25Retriever
    from app.documents.services.fusion import ReciprocalRankFusionEngine
    from app.documents.services.mmr import DefaultMMRSelector
    from app.documents.services.reranker import IdentityReranker

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

    sparse_index = InMemoryBM25Index(
        chunk_repo=chunk_repo,
        index_cache=index_cache,
    )
    sparse_retriever = BM25Retriever(sparse_index=sparse_index)

    fusion_engine = ReciprocalRankFusionEngine(rrf_k=settings.RRF_K)
    mmr_selector = DefaultMMRSelector()
    reranker = IdentityReranker()

    return RetrievalService(
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion_engine=fusion_engine,
        mmr_selector=mmr_selector,
        reranker=reranker,
        chunk_repo=chunk_repo,
        enable_hybrid_search=settings.ENABLE_HYBRID_SEARCH,
        enable_mmr=settings.ENABLE_MMR,
        enable_reranker=settings.ENABLE_RERANKER,
        vector_top_k=settings.VECTOR_TOP_K,
        bm25_top_k=settings.BM25_TOP_K,
        mmr_lambda=settings.MMR_LAMBDA,
        rerank_top_k=settings.RERANK_TOP_K,
    )


# --- Chat & LLM Orchestration Component Dependency Injection ---

def get_token_estimator():
    from app.chat.services.token_estimator import CharacterTokenEstimator
    return CharacterTokenEstimator()


def get_llm_provider():
    from app.chat.infrastructure.openai_provider import OpenAIProvider
    from app.chat.infrastructure.gemini_provider import GeminiProvider
    from app.chat.infrastructure.failover_proxy import ProviderFailoverProxy

    primary = GeminiProvider(api_key=settings.GEMINI_API_KEY)
    backup = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
    
    # ProviderFailoverProxy coordinates fallback policies
    return ProviderFailoverProxy(
        primary=primary,
        backup=backup,
        failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
    )


# Global PromptBuilder instance cached system prompt at startup
_prompt_builder_instance = None


def get_prompt_builder():
    global _prompt_builder_instance
    if _prompt_builder_instance is None:
        from app.chat.services.prompt_builder import PromptBuilder
        _prompt_builder_instance = PromptBuilder(system_prompt_path=settings.SYSTEM_PROMPT_PATH)
    return _prompt_builder_instance


def get_context_builder(
    token_estimator=Depends(get_token_estimator),
) -> Any:
    from app.chat.services.context_builder import ContextBuilder
    return ContextBuilder(
        token_estimator=token_estimator,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
    )


def get_conversation_repository(db: Session = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import SQLAlchemyConversationRepository
    return SQLAlchemyConversationRepository(db)


def get_message_repository(db: Session = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import SQLAlchemyMessageRepository
    return SQLAlchemyMessageRepository(db)


def get_summary_repository(db: Session = Depends(get_db)) -> Any:
    from app.chat.infrastructure.persistence.repositories import SQLAlchemySummaryRepository
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


def get_history_rewrite_cache(request: Request = None) -> Any:
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
    model = (
        settings.GEMINI_CHAT_MODEL
        if settings.LLM_PROVIDER == "gemini"
        else settings.OPENAI_CHAT_MODEL
    )
    return LLMHistoryRewriter(llm_provider, model=model, cache=cache, cache_ttl_seconds=3600)


def get_conversation_title_generator(
    llm_provider=Depends(get_llm_provider),
) -> Any:
    from app.chat.services.title_generator import LLMConversationTitleGenerator
    model = (
        settings.GEMINI_CHAT_MODEL
        if settings.LLM_PROVIDER == "gemini"
        else settings.OPENAI_CHAT_MODEL
    )
    return LLMConversationTitleGenerator(llm_provider, model=model)


def get_conversation_context_builder() -> Any:
    from app.chat.services.conversation_context_builder import ConversationContextBuilder
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
    db = db_session_factory()
    try:
        from app.chat.infrastructure.persistence.repositories import (
            SQLAlchemyMessageRepository,
            SQLAlchemySummaryRepository,
        )
        from app.chat.services.conversation_summarizer import LLMConversationSummarizer

        message_repo = SQLAlchemyMessageRepository(db)
        summary_repo = SQLAlchemySummaryRepository(db)

        count = await message_repo.count_messages(conversation_id)
        if count >= settings.SUMMARY_TRIGGER_MESSAGES:
            model = (
                settings.GEMINI_CHAT_MODEL
                if settings.LLM_PROVIDER == "gemini"
                else settings.OPENAI_CHAT_MODEL
            )
            summarizer = LLMConversationSummarizer(
                llm_provider=llm_provider_instance,
                summary_repo=summary_repo,
                message_repo=message_repo,
                model=model,
                summary_max_tokens=settings.SUMMARY_MAX_TOKENS,
            )

            # Fetch all messages in chronological order
            messages = await message_repo.get_recent_messages(conversation_id, limit=1000)
            up_to_idx = count - settings.MAX_MESSAGES_PER_CONTEXT - 1
            if up_to_idx >= 0:
                up_to_msg = messages[up_to_idx]
                await summarizer.summarize(conversation_id, up_to_msg.id)
                db.commit()
    except Exception as e:
        logger.exception(f"Error during background summarization task: {e}")
    finally:
        db.close()


def get_event_dispatcher(
    request: Request = None,
    llm_provider=Depends(get_llm_provider),
) -> Any:
    global _dispatcher_instance
    if _dispatcher_instance is None:
        from app.chat.domain.events import ConversationMessageCreated
        from app.documents.infrastructure.event_dispatcher import SimpleEventDispatcher
        from app.documents.infrastructure.tasks import FastAPIBackgroundTasksQueue

        _dispatcher_instance = SimpleEventDispatcher()

        def handle_message_added(event: ConversationMessageCreated) -> None:
            # Resolve task queue
            if request and hasattr(request, "background_tasks"):
                task_queue = FastAPIBackgroundTasksQueue(request.background_tasks)
            else:
                from app.documents.infrastructure.tasks import SyncTaskQueue
                task_queue = SyncTaskQueue()

            session_factory = getattr(request.app.state, "db_session_factory", None) if request else None
            if not session_factory:
                from sqlalchemy.orm import sessionmaker
                from app.db.session import init_postgres_engine
                engine = init_postgres_engine(settings.DATABASE_URL)
                session_factory = sessionmaker(bind=engine)

            task_queue.enqueue(
                run_background_summarization,
                event.conversation_id,
                event.message_id,
                session_factory,
                llm_provider,
            )

        _dispatcher_instance.register(ConversationMessageCreated, handle_message_added)

    return _dispatcher_instance


def get_conversation_manager(
    conversation_repo=Depends(get_conversation_repository),
    message_repo=Depends(get_message_repository),
    summary_repo=Depends(get_summary_repository),
    access_service=Depends(get_conversation_access_service),
    memory=Depends(get_conversation_memory),
    rewriter=Depends(get_history_rewriter),
    title_generator=Depends(get_conversation_title_generator),
    event_dispatcher=Depends(get_event_dispatcher),
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
    model = (
        settings.GEMINI_CHAT_MODEL
        if settings.LLM_PROVIDER == "gemini"
        else settings.OPENAI_CHAT_MODEL
    )
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


def get_tool_registry(
    retrieval_service=Depends(get_retrieval_service)
) -> Any:
    from app.chat.services.tool_registry import ToolRegistry
    from app.chat.services.tools.semantic_search import SearchKnowledgeTool
    from app.chat.services.tools.document_retrieval import RetrieveDocumentTool
    from app.chat.services.tools.chunk_retrieval import RetrieveChunkTool
    from app.chat.services.tools.citation_lookup import CitationLookupTool
    from app.chat.services.tools.calculator import CalculatorTool
    from app.chat.services.tools.datetime import DateTimeTool

    tools = [
        SearchKnowledgeTool(retrieval_service),
        RetrieveDocumentTool(),
        RetrieveChunkTool(),
        CitationLookupTool(),
        CalculatorTool(),
        DateTimeTool(),
    ]
    registry = ToolRegistry(tools)
    # Register aliases
    registry.register(tools[0], aliases=["semantic_search", "document_search"])
    return registry


def get_tool_discovery_service(
    registry=Depends(get_tool_registry)
) -> Any:
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


def get_chat_orchestrator(
    retrieval_service=Depends(get_retrieval_service),
    prompt_builder=Depends(get_prompt_builder),
    llm_provider=Depends(get_llm_provider),
    token_estimator=Depends(get_token_estimator),
    conversation_manager=Depends(get_conversation_manager),
    conversation_context_builder=Depends(get_conversation_context_builder),
    agent_executor=Depends(get_agent_executor),
) -> Any:
    from app.chat.services.chat_orchestrator import ChatOrchestrator
    from app.chat.services.llm_generation_service import LLMGenerationService

    llm_gen = LLMGenerationService(llm_provider)
    model = (
        settings.GEMINI_CHAT_MODEL
        if settings.LLM_PROVIDER == "gemini"
        else settings.OPENAI_CHAT_MODEL
    )
    return ChatOrchestrator(
        retrieval_service=retrieval_service,
        prompt_builder=prompt_builder,
        llm_generation_service=llm_gen,
        token_estimator=token_estimator,
        conversation_manager=conversation_manager,
        context_builder=conversation_context_builder,
        agent_executor=agent_executor,
        model=model,
        temperature=settings.TEMPERATURE,
        max_response_tokens=settings.MAX_RESPONSE_TOKENS,
        system_prompt_tokens_limit=settings.SYSTEM_PROMPT_TOKENS,
        max_context_tokens=settings.MAX_CONTEXT_TOKENS,
        reserved_completion_tokens=settings.RESERVED_COMPLETION_TOKENS,
        max_memory_tokens=settings.MAX_MEMORY_TOKENS,
        enable_conversation_memory=settings.ENABLE_CONVERSATION_MEMORY,
        enable_tool_calling=settings.ENABLE_TOOL_CALLING,
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


def get_conversation_evaluator():
    from app.evaluation.services.conversation_evaluator import ConversationEvaluator
    return ConversationEvaluator()


def get_evaluation_runner(
    retrieval_evaluator=Depends(get_retrieval_evaluator),
    agent_evaluator=Depends(get_agent_evaluator),
    tool_evaluator=Depends(get_tool_evaluator),
    conversation_evaluator=Depends(get_conversation_evaluator),
    ragas_provider=Depends(get_ragas_provider),
    deepeval_provider=Depends(get_deepeval_provider)
):
    from app.evaluation.runners.evaluation_runner import EvaluationRunner
    return EvaluationRunner(
        retrieval_evaluator=retrieval_evaluator,
        agent_evaluator=agent_evaluator,
        tool_evaluator=tool_evaluator,
        conversation_evaluator=conversation_evaluator,
        ragas_provider=ragas_provider,
        deepeval_provider=deepeval_provider
    )


def get_benchmark_runner(
    evaluation_runner=Depends(get_evaluation_runner)
):
    from app.evaluation.runners.benchmark_runner import BenchmarkRunner
    return BenchmarkRunner(evaluation_runner=evaluation_runner)


def get_regression_runner():
    from app.evaluation.runners.regression_runner import RegressionRunner
    return RegressionRunner()


def get_report_generator():
    from app.evaluation.reports.report_generator import ReportGenerator
    return ReportGenerator(output_dir=settings.EVALUATION_RESULTS_DIR)


# --- Production Backend Layer Dependency Providers ---

_cache_instance = None

def get_cache(request: Request = None) -> Any:
    global _cache_instance
    if _cache_instance is None:
        from app.core.cache.memory_cache import InMemoryCache
        from app.core.cache.redis_cache import RedisCache
        from app.core.cache.multi_tier import MultiTierCache

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


def get_distributed_lock(request: Request = None) -> Any:
    from app.core.cache.lock import RedisDistributedLock, InMemoryDistributedLock
    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    if redis_client:
        return RedisDistributedLock(redis_client)
    return InMemoryDistributedLock()


def get_rate_limiter(request: Request = None) -> Any:
    from app.core.security.rate_limiter import RateLimiter
    redis_client = None
    if request:
        try:
            redis_client = getattr(request.app.state, "redis", None)
        except Exception:
            pass
    return RateLimiter(
        redis_client=redis_client,
        requests_per_minute=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
        burst=settings.RATE_LIMIT_BURST
    )


def get_idempotency_manager(request: Request = None) -> Any:
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


def get_resource_quota_service(db: Session = Depends(get_db), request: Request = None) -> Any:
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
        from app.core.cost.pricing_provider import YAMLPricingProvider
        import os
        yaml_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "core", "cost", "pricing.yaml"
        )
        _pricing_provider = YAMLPricingProvider(yaml_path)
    return _pricing_provider


_feature_flag_service = None

def get_feature_flag_service() -> Any:
    global _feature_flag_service
    if _feature_flag_service is None:
        from app.core.feature_flags.flags import FeatureFlagService, SettingsFeatureFlagProvider
        provider = SettingsFeatureFlagProvider()
        _feature_flag_service = FeatureFlagService(provider)
    return _feature_flag_service


_event_bus_instance = None

def get_event_bus(request: Request = None) -> Any:
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


