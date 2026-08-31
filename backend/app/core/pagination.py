import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.core.config import settings


class InvalidCursorException(Exception):
    """Raised when a pagination cursor is invalid, malformed, expired, tampered, or context-mismatched."""

    pass


class CursorDirection(str, Enum):
    NEXT = "next"
    PREV = "prev"


class CursorPayload(BaseModel):
    v: int = 1
    ts: str  # ISO-8601 UTC timestamp string
    id: str  # UUID string
    dir: CursorDirection
    res: str  # Resource identifier: 'conv' | 'msg'
    ctx: str  # Context binding ID: user_id or conversation_id
    iat: int  # Issued-at timestamp (seconds)
    exp: int  # Expiration timestamp (seconds)


class CursorPage[T](BaseModel):
    items: list[T]
    limit: int
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_next_page: bool = False
    has_prev_page: bool = False
    has_more: bool = False  # Backward-compatible alias for has_next_page

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> T:
        return self.items[index]

    def __iter__(self):
        return iter(self.items)


class CursorSigner:
    @staticmethod
    def _get_signing_key() -> bytes:
        key_val = getattr(settings, "CURSOR_SIGNING_KEY", None)
        if not key_val:
            key_val = getattr(settings, "JWT_SECRET", None) or getattr(
                settings, "SECRET_KEY", None
            )
        key_str = str(key_val) if key_val else "default-fallback-cursor-signing-key-32b"
        return key_str.encode("utf-8")

    @classmethod
    def encode(
        cls,
        created_at: datetime,
        record_id: UUID,
        direction: CursorDirection,
        resource_type: str,
        context_id: UUID | str,
        ttl_seconds: int | None = None,
    ) -> str:
        """
        Encodes a database boundary (timestamp + UUID) into a signed opaque token.
        Wire format: base64url(canonical_json) + "." + base64url(hmac_sha256(canonical_json))
        """
        now_ts = int(time.time())
        ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else getattr(settings, "CURSOR_TTL_SECONDS", 604800)
        )
        exp_ts = now_ts + ttl

        # Ensure timestamp is UTC ISO string with microsecond precision
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        ts_iso = created_at.astimezone(UTC).isoformat()

        payload = {
            "ctx": str(context_id),
            "dir": direction.value,
            "exp": exp_ts,
            "iat": now_ts,
            "id": str(record_id),
            "res": resource_type,
            "ts": ts_iso,
            "v": 1,
        }

        canonical_json_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        key = cls._get_signing_key()
        sig = hmac.new(key, canonical_json_bytes, hashlib.sha256).digest()

        encoded_payload = (
            base64.urlsafe_b64encode(canonical_json_bytes).decode("ascii").rstrip("=")
        )
        encoded_sig = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

        return f"{encoded_payload}.{encoded_sig}"

    @classmethod
    def decode(
        cls,
        token: str,
        expected_resource_type: str,
        expected_context_id: UUID | str | None = None,
    ) -> CursorPayload:
        """
        Decodes and validates a signed cursor token.
        Enforces HMAC authenticity, TTL expiration, resource type, and context binding.
        """
        if not token or not isinstance(token, str):
            raise InvalidCursorException("Missing or empty cursor token.")

        parts = token.strip().split(".")
        if len(parts) != 2:
            raise InvalidCursorException(
                "Malformed cursor: expected payload.signature format."
            )

        encoded_payload, encoded_sig = parts[0], parts[1]

        # Pad base64url strings if necessary
        def _pad_b64(s: str) -> str:
            return s + "=" * (-len(s) % 4)

        try:
            canonical_json_bytes = base64.urlsafe_b64decode(_pad_b64(encoded_payload))
            provided_sig = base64.urlsafe_b64decode(_pad_b64(encoded_sig))
        except Exception as e:
            raise InvalidCursorException(f"Malformed cursor encoding: {e}") from e

        # Validate signature
        key = cls._get_signing_key()
        expected_sig = hmac.new(key, canonical_json_bytes, hashlib.sha256).digest()

        if not hmac.compare_digest(provided_sig, expected_sig):
            raise InvalidCursorException(
                "Cursor signature verification failed: invalid or tampered cursor."
            )

        try:
            data = json.loads(canonical_json_bytes.decode("utf-8"))
            payload = CursorPayload(**data)
        except Exception as e:
            raise InvalidCursorException(
                f"Invalid cursor payload structure: {e}"
            ) from e

        # Validate Expiry
        now_ts = int(time.time())
        if payload.exp < now_ts:
            raise InvalidCursorException(
                f"Cursor has expired (exp: {payload.exp}, current: {now_ts})."
            )

        # Validate Resource Type
        if payload.res != expected_resource_type:
            raise InvalidCursorException(
                f"Cursor resource mismatch: expected '{expected_resource_type}', got '{payload.res}'."
            )

        # Validate Context Binding
        if expected_context_id is not None:
            if str(payload.ctx) != str(expected_context_id):
                raise InvalidCursorException(
                    "Cursor context mismatch: cursor cannot be used for this resource."
                )

        return payload

    @classmethod
    def parse_boundary(
        cls,
        token: str,
        expected_resource_type: str,
        expected_context_id: UUID | str | None = None,
    ) -> tuple[datetime, UUID, CursorDirection]:
        """
        Convenience method returning parsed (datetime, UUID, direction).
        """
        payload = cls.decode(token, expected_resource_type, expected_context_id)
        try:
            ts_dt = datetime.fromisoformat(payload.ts)
            rec_id = UUID(payload.id)
            return ts_dt, rec_id, payload.dir
        except Exception as e:
            raise InvalidCursorException(f"Invalid cursor boundary values: {e}") from e
