import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.evaluation import router as evaluation_router
from app.api.v1.health import router as health_router
from app.api.v1.observability import router as observability_router
from app.api.v1.search import router as search_router
from app.api.v1.user_settings import router as user_settings_router
from app.auth.infrastructure.crypto.token_provider import JWTTokenProvider
from app.core.config import settings
from app.core.context.request_context import RequestContext, current_request_context
from app.core.logger import (
    client_ip_ctx,
    request_duration_ctx,
    request_id_ctx,
    request_method_ctx,
    request_path_ctx,
    request_status_ctx,
    setup_logging,
)
from app.core.startup import (
    run_startup_validations,
    seed_admin_user,
    verify_alembic_migrations,
    verify_postgres_connectivity,
)
from app.db.models import Base  # noqa: F401  (side-effect: full model registration)

setup_logging(settings.LOG_FORMAT, settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


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

        # Initialize OpenTelemetry and Prometheus subsystems
        from app.core.telemetry import init_telemetry, shutdown_telemetry

        init_telemetry(app)

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
        await seed_admin_user(app.state.db_session_factory)

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
                model_name=settings.EMBEDDING_MODEL,
                dimension=settings.EMBEDDING_DIMENSION,
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

            # Durable Ingestion Reaper
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

        shutdown_telemetry()
        logger.info("Lifespan connections clean up completed.")
    except Exception as e:
        logger.error(f"Error occurred during shutdown teardown: {e}", exc_info=True)


app = FastAPI(
    title=settings.PROJECT_NAME,
    summary="FusionRAG (Enterprise Hybrid Retrieval-Augmented Generation) API backend combining dense vectors and BM25 sparse search with cross-encoder reranking.",
    description="""
# FusionRAG API

Production-ready, highly observable, verifiable AI Document QA and retrieval platform.

## Features
* **Hybrid Retrieval**: Dense embeddings (Qdrant) + BM25 Sparse Search fused via Reciprocal Rank Fusion (RRF).
* **Neural Reranking**: Cross-Encoder model scoring for high-precision context relevance.
* **Evaluation Framework**: Automated Faithfulness, Context Relevancy, and Hallucination metric pipelines.
* **Streaming QA**: Low-latency token streaming with inline grounded citations.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# 3. Request ID middleware


def resolve_route_template(request: Request) -> str:
    """
    Resolves the parameterized route pattern (e.g. /api/v1/conversations/{conversation_id})
    from the FastAPI router to prevent high-cardinality label explosion in Prometheus.
    Falls back to dynamic segment sanitization ({id}) if router match is not available.
    """
    app = request.app
    if app and hasattr(app, "routes"):
        for route in app.routes:
            match, _ = route.matches(request.scope)
            if match.name == "FULL":
                return getattr(route, "path", request.url.path)

    path = request.url.path
    parts = path.split("/")
    sanitized = []
    for p in parts:
        if (len(p) == 36 and "-" in p) or p.isdigit():
            sanitized.append("{id}")
        else:
            sanitized.append(p)
    return "/".join(sanitized) or "/unknown"


class ProductionMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive middleware pipeline:
    - Graceful shutdown check (returns 503 if draining)
    - Correlation ID tracking (X-Request-ID)
    - OpenTelemetry Distributed Tracing (HTTP Server Span + W3C Context)
    - Prometheus HTTP Server Metrics (Requests, Duration, In-Flight)
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

        from opentelemetry.trace import SpanKind

        from app.core.telemetry import (
            HTTP_SERVER_ACTIVE_REQUESTS,
            HTTP_SERVER_DURATION,
            HTTP_SERVER_REQUESTS,
            extract_trace_context,
            get_current_trace_id,
            get_tracer,
            hash_user_id,
            mask_ip_address,
        )

        tracer = get_tracer("fusion-rag.http")
        parent_ctx = extract_trace_context(dict(request.headers))

        route_template = resolve_route_template(request)

        HTTP_SERVER_ACTIVE_REQUESTS.inc()
        start_time = time.perf_counter()

        with tracer.start_as_current_span(
            "http.server.request",
            context=parent_ctx,
            kind=SpanKind.SERVER,
        ) as root_span:
            otel_trace_id = get_current_trace_id()
            if otel_trace_id:
                context.trace_id = otel_trace_id

            root_span.set_attribute("http.method", request.method)
            root_span.set_attribute("http.route", route_template)
            if context.client_ip:
                masked_ip = mask_ip_address(context.client_ip)
                if masked_ip:
                    root_span.set_attribute("client.address", masked_ip)
            if user_id:
                h_uid = hash_user_id(user_id)
                if h_uid:
                    root_span.set_attribute("user.id", h_uid)

            try:
                logger.info("Request processing started")
                response = await call_next(request)

                duration_s = time.perf_counter() - start_time
                duration_ms = duration_s * 1000
                request_status_ctx.set(response.status_code)
                request_duration_ctx.set(round(duration_ms, 2))
                if response.status_code >= 500:
                    request.app.state.error_count = (
                        getattr(request.app.state, "error_count", 0) + 1
                    )

                root_span.set_attribute("http.status_code", response.status_code)

                # Record Prometheus metrics with bounded labels
                try:
                    HTTP_SERVER_REQUESTS.labels(
                        method=request.method,
                        route=route_template,
                        status_code=str(response.status_code),
                    ).inc()
                    HTTP_SERVER_DURATION.labels(
                        method=request.method,
                        route=route_template,
                        status_code=str(response.status_code),
                    ).observe(duration_s)
                except Exception:
                    pass

                logger.info(
                    f"Request processing completed - Duration: {duration_ms:.2f}ms"
                )

                # Inject correlation ID and Secure Headers
                response.headers["X-Request-ID"] = req_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = (
                    "geolocation=(), camera=(), microphone=()"
                )
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; frame-ancestors 'none'; object-src 'none';"
                )
                if settings.is_production and settings.COOKIE_SECURE:
                    response.headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )

                return response
            except Exception as e:
                duration_s = time.perf_counter() - start_time
                duration_ms = duration_s * 1000
                request_status_ctx.set(500)
                request_duration_ctx.set(round(duration_ms, 2))
                root_span.set_attribute("http.status_code", 500)
                root_span.record_exception(e)

                try:
                    HTTP_SERVER_REQUESTS.labels(
                        method=request.method,
                        route=route_template,
                        status_code="500",
                    ).inc()
                    HTTP_SERVER_DURATION.labels(
                        method=request.method,
                        route=route_template,
                        status_code="500",
                    ).observe(duration_s)
                except Exception:
                    pass

                logger.exception(f"Request crashed during execution: {e}")
                raise e
            finally:
                HTTP_SERVER_ACTIVE_REQUESTS.dec()
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


register_exception_handlers(app)


app.include_router(health_router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(search_router, prefix=settings.API_V1_STR)
app.include_router(chat_router, prefix=settings.API_V1_STR)
app.include_router(conversations_router, prefix=f"{settings.API_V1_STR}/conversations")
app.include_router(evaluation_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(observability_router, prefix=settings.API_V1_STR)
app.include_router(user_settings_router, prefix=settings.API_V1_STR)


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus scraping endpoint backed by live prometheus-client registry."""
    from app.core.telemetry import export_prometheus_metrics

    return Response(
        content=export_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/robots.txt", response_class=Response)
def backend_robots_txt():
    """Robots exclusion policy for FastAPI Render backend."""
    content = (
        "User-agent: *\n"
        "Allow: /docs\n"
        "Allow: /redoc\n"
        f"Allow: {settings.API_V1_STR}/openapi.json\n"
        f"Disallow: {settings.API_V1_STR}/\n"
        "Disallow: /metrics\n"
    )
    return Response(content=content, media_type="text/plain; charset=utf-8")


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def root_route():
    return {
        "status": "ok",
        "message": f"Welcome to the {settings.PROJECT_NAME} API.",
        "health_liveness_endpoint": f"{settings.API_V1_STR}/health/liveness",
        "health_readiness_endpoint": f"{settings.API_V1_STR}/health/readiness",
    }
