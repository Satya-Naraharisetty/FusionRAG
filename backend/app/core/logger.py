import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Thread-safe ContextVars to store request-specific information across async calls
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
request_method_ctx: ContextVar[str | None] = ContextVar("request_method", default=None)
request_path_ctx: ContextVar[str | None] = ContextVar("request_path", default=None)
client_ip_ctx: ContextVar[str | None] = ContextVar("client_ip", default=None)
request_status_ctx: ContextVar[int | None] = ContextVar("request_status", default=None)
request_duration_ctx: ContextVar[float | None] = ContextVar(
    "request_duration", default=None
)


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records into structured, single-line JSON objects.
    """

    def format(self, record: logging.LogRecord) -> str:
        span_id = None
        otel_trace_id = None
        try:
            from app.core.telemetry import (
                get_current_span_id,
                get_current_trace_id,
            )

            otel_trace_id = get_current_trace_id()
            span_id = get_current_span_id()
        except Exception:
            pass

        try:
            from app.core.context.request_context import current_request_context

            ctx = current_request_context.get()
            user_id = ctx.user_id if ctx else None
            trace_id = otel_trace_id or (ctx.trace_id if ctx else None)
            req_id = ctx.request_id if ctx else request_id_ctx.get()
            ip = ctx.client_ip if ctx else client_ip_ctx.get()
        except Exception:
            user_id = None
            trace_id = otel_trace_id
            req_id = request_id_ctx.get()
            ip = client_ip_ctx.get()

        log_payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "level": record.levelname,
            "request_id": req_id,
            "trace_id": trace_id or req_id,
            "span_id": span_id,
            "user_id": user_id,
            "method": request_method_ctx.get(),
            "path": request_path_ctx.get(),
            "status_code": request_status_ctx.get(),
            "duration_ms": request_duration_ctx.get(),
            "client_ip": ip,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Format exception tracebacks if present
        if record.exc_info:
            log_payload["exception_trace"] = self.formatException(record.exc_info)

        # Remove keys with None values to maintain compact JSON records
        filtered_payload = {k: v for k, v in log_payload.items() if v is not None}
        return json.dumps(filtered_payload)


class CustomConsoleFormatter(logging.Formatter):
    """
    Formats log records into a clean, human-readable text output for local debugging.
    """

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        req_id_str = f" [{req_id}]" if req_id else ""

        method = request_method_ctx.get()
        path = request_path_ctx.get()
        req_path_str = f" {method} {path} -" if method and path else ""

        exc_str = ""
        if record.exc_info:
            exc_str = f"\n{self.formatException(record.exc_info)}"

        return (
            f"{datetime.now(UTC).isoformat()} [{record.levelname}]{req_id_str} "
            f"{record.name}:{req_path_str} {record.getMessage()}{exc_str}"
        )


def setup_logging(log_format: str = "TEXT", log_level: str = "INFO") -> None:
    """
    Initializes root logging handler configurations.
    """
    root_logger = logging.getLogger()

    # Remove default uvicorn handlers to avoid duplicate log printing
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set up stdout console stream handler
    stream_handler = logging.StreamHandler(sys.stdout)

    if log_format.upper() == "JSON":
        stream_handler.setFormatter(StructuredJsonFormatter())
    else:
        stream_handler.setFormatter(CustomConsoleFormatter())

    root_logger.addHandler(stream_handler)
    root_logger.setLevel(logging.getLevelName(log_level.upper()))

    # Reconfigure uvicorn loggers to route via our custom formatter
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.handlers = []
        sub_logger.propagate = True
