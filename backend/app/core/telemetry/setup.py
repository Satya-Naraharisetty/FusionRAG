import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    Sampler,
    TraceIdRatioBased,
)
from opentelemetry.trace import NoOpTracerProvider, Tracer

from app.core.config import settings

logger = logging.getLogger(__name__)

_tracer_provider: TracerProvider | None = None
_is_initialized: bool = False


def init_telemetry(app: Any = None) -> None:
    """
    Initializes the OpenTelemetry TracerProvider, MeterProvider, and Span Exporters.
    Completely fail-silent: any telemetry initialization error logs a warning without crashing.
    """
    global _tracer_provider, _is_initialized
    if _is_initialized:
        return

    if not getattr(settings, "ENABLE_TELEMETRY", True) or not getattr(
        settings, "ENABLE_TRACING", True
    ):
        logger.info("OpenTelemetry tracing is disabled via configuration.")
        trace.set_tracer_provider(NoOpTracerProvider())
        _is_initialized = True
        return

    try:
        service_name = getattr(settings, "OTEL_SERVICE_NAME", "hybrid-rag-backend")
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                "environment": getattr(settings, "ENVIRONMENT", "production"),
            }
        )

        # Sampler configuration
        sample_ratio = getattr(settings, "OTEL_TRACES_SAMPLER_RATIO", 1.0)
        sampler: Sampler
        if sample_ratio >= 1.0:
            sampler = ALWAYS_ON
        elif sample_ratio <= 0.0:
            sampler = ALWAYS_OFF
        else:
            sampler = ParentBased(root=TraceIdRatioBased(sample_ratio))

        provider = TracerProvider(resource=resource, sampler=sampler)

        endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None)
        import sys

        is_test_env = (
            "pytest" in sys.modules
            or getattr(settings, "ENVIRONMENT", "").lower() == "testing"
            or getattr(settings, "is_testing", False)
        )

        if endpoint and endpoint.strip() and not is_test_env:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(endpoint=endpoint, timeout=2.0)
                processor = BatchSpanProcessor(
                    exporter,
                    max_queue_size=2048,
                    schedule_delay_millis=500,
                    max_export_batch_size=512,
                )
                provider.add_span_processor(processor)
                logger.info(
                    f"OpenTelemetry OTLP gRPC span exporter configured for {endpoint}"
                )
            except Exception as exp_err:
                logger.warning(
                    f"Could not initialize OTLPSpanExporter ({exp_err}). Traces will be collected in-memory."
                )
        else:
            logger.debug("Local/testing mode; remote OTLP exporter bypassed.")

        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        _is_initialized = True
        logger.info("OpenTelemetry tracing subsystem initialized successfully.")

    except Exception as e:
        logger.warning(
            f"Failed to initialize OpenTelemetry: {e}. Falling back to NoOpTracer."
        )
        trace.set_tracer_provider(NoOpTracerProvider())
        _is_initialized = True


def shutdown_telemetry() -> None:
    """
    Flushes remaining spans and cleanly shuts down the TracerProvider.
    """
    global _tracer_provider, _is_initialized
    if _tracer_provider and hasattr(_tracer_provider, "shutdown"):
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry TracerProvider shut down cleanly.")
        except Exception as e:
            logger.warning(f"Error shutting down OpenTelemetry: {e}")
    _is_initialized = False


def get_tracer(name: str = "hybrid-rag") -> Tracer:
    """
    Returns an OpenTelemetry tracer instance for creating spans.
    """
    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    return trace.get_tracer(name)


def set_tracer_provider_for_test(provider: TracerProvider | None) -> None:
    """
    Explicitly assigns a tracer provider for unit/integration testing with InMemorySpanExporter.
    """
    global _tracer_provider
    _tracer_provider = provider
