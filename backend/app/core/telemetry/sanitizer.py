import hashlib
import re
from typing import Any
from uuid import UUID

from app.chat.domain.agent_observability import (
    SENSITIVE_KEYS as _AGENT_SENSITIVE_KEYS,
)
from app.chat.domain.agent_observability import (
    hash_user_id as _hash_user_id,
)
from app.chat.domain.agent_observability import (
    sanitize_telemetry_data as _sanitize_telemetry_data,
)

# Extended sensitive key patterns that must be redacted
SENSITIVE_KEYS = set(_AGENT_SENSITIVE_KEYS) | {
    "token",
    "database_url",
    "postgres_password",
    "redis_password",
    "jwt_secret",
    "gemini_api_key",
    "qdrant_api_key",
    "jina_api_key",
    "s3_secret_access_key",
}

# Regex to scrub Bearer tokens and passwords in raw strings/error messages
_AUTH_BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE)
_KEY_SECRET_PATTERN = re.compile(
    r"(key|secret|password|token|api_key|apikey)=['\"][^'\"]+['\"]",
    re.IGNORECASE,
)
_IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def hash_user_id(user_id: UUID | str | None) -> str | None:
    """Produces a non-reversible SHA-256 hash of user ID for privacy-safe telemetry correlation."""
    return _hash_user_id(user_id)


def mask_ip_address(ip: str | None) -> str | None:
    """Anonymizes IP address to /24 subnet or hash representation."""
    if not ip:
        return None
    ip_str = str(ip).strip()
    parts = ip_str.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    # For IPv6 or other formats
    return hashlib.sha256(ip_str.encode("utf-8")).hexdigest()[:12]


def sanitize_error_string(error: str | None, max_length: int = 1000) -> str:
    """Sanitizes error string by scrubbing potential tokens, keys, and secrets."""
    if not error:
        return ""
    sanitized = _AUTH_BEARER_PATTERN.sub(r"\1[REDACTED]", str(error))
    sanitized = _KEY_SECRET_PATTERN.sub(r"\1=[REDACTED]", sanitized)
    return sanitized[:max_length]


def sanitize_telemetry_data(
    data: Any,
    max_str_len: int = 500,
    max_keys: int = 50,
    depth: int = 0,
    max_depth: int = 5,
) -> Any:
    """
    Recursively sanitizes dictionaries, lists, models, and payloads for telemetry.
    Redacts credentials, tokens, passwords, raw prompts, and document contents.
    """
    if isinstance(data, str):
        # Scrub Bearer tokens or secret assignments if found in strings
        cleaned = _AUTH_BEARER_PATTERN.sub(r"\1[REDACTED]", data)
        cleaned = _KEY_SECRET_PATTERN.sub(r"\1=[REDACTED]", cleaned)
        return _sanitize_telemetry_data(
            cleaned, max_str_len, max_keys, depth, max_depth
        )
    return _sanitize_telemetry_data(data, max_str_len, max_keys, depth, max_depth)


def sanitize_span_attribute(
    value: Any, max_str_len: int = 256
) -> str | int | float | bool:
    """
    Converts and sanitizes an attribute value to a safe primitive type for OpenTelemetry spans.
    """
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        sanitized = sanitize_telemetry_data(value, max_str_len=max_str_len)
        import json

        try:
            return json.dumps(sanitized)[:max_str_len]
        except Exception:
            return str(sanitized)[:max_str_len]

    str_val = str(value)
    sanitized_str = sanitize_error_string(str_val, max_length=max_str_len)
    return sanitized_str
