import logging
from typing import Any

from opentelemetry import context, trace
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

logger = logging.getLogger(__name__)

_propagator = TraceContextTextMapPropagator()


def inject_trace_context(carrier: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Injects the active OpenTelemetry trace context (traceparent, tracestate) into a dictionary carrier.
    Ideal for serializing context into Redis Stream job payloads or HTTP headers.
    """
    if carrier is None:
        carrier = {}
    try:
        _propagator.inject(carrier)
    except Exception as e:
        logger.debug(f"Failed to inject trace context: {e}")
    return carrier


def extract_trace_context(
    carrier: dict[str, Any] | None = None,
) -> context.Context:
    """
    Extracts W3C trace context from a dictionary carrier and returns the OpenTelemetry Context.
    """
    if not carrier:
        return context.get_current()
    try:
        # Convert any byte keys/values to strings for header extraction
        str_carrier = {
            (k.decode("utf-8") if isinstance(k, bytes) else str(k)): (
                v.decode("utf-8") if isinstance(v, bytes) else str(v)
            )
            for k, v in carrier.items()
        }
        return _propagator.extract(str_carrier)
    except Exception as e:
        logger.debug(f"Failed to extract trace context: {e}")
        return context.get_current()


def get_current_trace_id() -> str | None:
    """
    Returns the current 32-hex character trace ID, or None if no span is active.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return trace.format_trace_id(span.get_span_context().trace_id)
    return None


def get_current_span_id() -> str | None:
    """
    Returns the current 16-hex character span ID, or None if no span is active.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return trace.format_span_id(span.get_span_context().span_id)
    return None
