import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.core.cache.interfaces import BaseCache
from app.core.config import settings
from app.core.security.crypto import EnvelopeEncryptionService, crypto_service

logger = logging.getLogger(__name__)


class RAGCacheService:
    """
    Production-grade caching domain service for RAG Q&A responses.

    Responsibilities:
    1. Deterministic, multi-tenant, active-version-scoped cache key generation.
    2. AES-256-GCM envelope encryption & decryption of cached payloads in Redis.
    3. Quality and agent execution plan gating to prevent caching stale or refused responses.
    4. Paced Server-Sent Events (SSE) stream replay for flawless frontend rendering.
    """

    def __init__(
        self,
        cache: BaseCache,
        crypto: EnvelopeEncryptionService | None = None,
        enabled: bool | None = None,
        response_ttl: int | None = None,
        stream_delay_ms: float | None = None,
        min_confidence: float | None = None,
    ) -> None:
        self._cache = cache
        self._crypto = crypto or crypto_service
        self._enabled = (
            enabled
            if enabled is not None
            else getattr(settings, "ENABLE_RAG_CACHE", True)
        )
        self._response_ttl = (
            response_ttl
            if response_ttl is not None
            else getattr(settings, "RAG_RESPONSE_CACHE_TTL_SECONDS", 3600)
        )
        self._stream_delay_ms = (
            stream_delay_ms
            if stream_delay_ms is not None
            else getattr(settings, "RAG_CACHE_STREAM_CHUNK_DELAY_MS", 5.0)
        )
        self._min_confidence = (
            min_confidence
            if min_confidence is not None
            else getattr(settings, "RAG_CACHE_MIN_CONFIDENCE", 0.70)
        )

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def compute_cache_key(
        self,
        user_id: UUID,
        conversation_id: UUID | None,
        parent_message_id: UUID | None,
        query: str,
        doc_versions: dict[UUID, int] | None = None,
        model: str = "gemini-3.5-flash-lite",
        temperature: float = 0.0,
    ) -> str:
        """
        Computes a deterministic SHA-256 cache key that guarantees tenant isolation,
        thread & branch lineage integrity, and immediate invalidation upon document updates.
        """
        normalized_query = " ".join(query.strip().lower().split())

        # Fingerprint all authorized documents and their active version numbers
        if doc_versions:
            doc_pairs = sorted(
                [(str(d_id), str(ver)) for d_id, ver in doc_versions.items()],
                key=lambda x: x[0],
            )
            doc_sig_str = ":".join(f"{d_id}@{ver}" for d_id, ver in doc_pairs)
        else:
            doc_sig_str = "no_docs"

        doc_sig = hashlib.sha256(doc_sig_str.encode("utf-8")).hexdigest()[:16]
        param_hash = hashlib.sha256(
            f"{normalized_query}:{model}:{temperature:.2f}".encode()
        ).hexdigest()[:16]

        conv_part = str(conversation_id) if conversation_id else "global"
        parent_part = str(parent_message_id) if parent_message_id else "root"

        return f"rag:ans:{user_id}:{conv_part}:{parent_part}:{doc_sig}:{param_hash}"

    def compute_global_cache_key(
        self,
        query: str,
        model: str = "gemini-3.5-flash-lite",
        temperature: float = 0.0,
    ) -> str:
        """
        Computes a global, tenant-agnostic cache key for standalone general knowledge queries
        that have zero document attachments and zero conversational dependencies.
        """
        normalized_query = " ".join(query.strip().lower().split())
        param_hash = hashlib.sha256(
            f"{normalized_query}:{model}:{temperature:.2f}".encode()
        ).hexdigest()[:16]
        return f"rag:ans:global:root:no_docs:{param_hash}"

    async def get_cached_response(
        self,
        key: str,
        user_dek: bytes | None = None,
        user_id: UUID | None = None,
        fallback_global_key: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Fetches and decrypts a cached RAG response payload.
        Falls back to global public cache for general queries if the user cache misses.
        Returns None on cache miss, decompression/decryption failure, or if disabled.
        """
        if not self._enabled:
            return None

        # 1. Check primary key (user-scoped)
        res = await self._get_payload_by_key(key, user_dek, user_id)
        if res is not None:
            return res

        # 2. Check global fallback key if provided
        if fallback_global_key and fallback_global_key != key:
            return await self._get_payload_by_key(
                fallback_global_key, user_dek=None, user_id=None
            )

        return None

    async def _get_payload_by_key(
        self,
        key: str,
        user_dek: bytes | None = None,
        user_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        try:
            cached_raw = await self._cache.get(key)
            if cached_raw is None:
                return None

            if isinstance(cached_raw, str):
                cached_data = json.loads(cached_raw)
            elif isinstance(cached_raw, dict):
                cached_data = cached_raw
            else:
                return None

            # Handle encrypted payload
            if cached_data.get("encrypted") is True:
                ciphertext = cached_data.get("ciphertext")
                if not ciphertext or not user_dek:
                    logger.warning(
                        "Encountered encrypted RAG cache item but no user DEK provided."
                    )
                    return None
                aad = str(user_id).encode("utf-8") if user_id else None
                decrypted_json = self._crypto.decrypt_text(
                    ciphertext, user_dek, aad=aad
                )
                return json.loads(decrypted_json)

            return cached_data
        except Exception as e:
            logger.warning(f"Error reading from RAG response cache for key {key}: {e}")
            return None

    async def set_cached_response(
        self,
        key: str,
        payload: dict[str, Any],
        user_id: UUID,
        user_dek: bytes | None = None,
        ttl: int | None = None,
        global_key: str | None = None,
    ) -> bool:
        """
        Encrypts (if DEK provided and enabled) and saves the RAG response payload to cache.
        Also persists to global public cache if a global_key is provided.
        """
        if not self._enabled:
            return False

        try:
            effective_ttl = ttl if ttl is not None else self._response_ttl
            json_str = json.dumps(payload, default=str)

            encrypt_enabled = getattr(settings, "RAG_CACHE_ENABLE_ENCRYPTION", True)
            if encrypt_enabled and user_dek:
                aad = str(user_id).encode("utf-8")
                ciphertext = self._crypto.encrypt_text(json_str, user_dek, aad=aad)
                cache_payload = {"encrypted": True, "ciphertext": ciphertext}
            else:
                cache_payload = payload

            await self._cache.set(key, cache_payload, ttl=effective_ttl)

            # Persist to global public cache for general queries with zero private citations
            if global_key and not payload.get("citations"):
                try:
                    await self._cache.set(global_key, payload, ttl=effective_ttl * 7)
                except Exception:
                    pass

            return True
        except Exception as e:
            logger.warning(f"Error writing to RAG response cache for key {key}: {e}")
            return False

    def should_cache_response(
        self,
        answer: str,
        diagnostics: Any = None,
        agent_diagnostics: Any = None,
        status: str = "completed",
    ) -> bool:
        """
        Evaluates quality gating to guarantee we never cache:
        1. Non-completed or error statuses.
        2. Empty or refusal answers ("I do not have enough evidence").
        3. Multi-agent runs that executed WebSearchAgent (live internet data).
        4. Evidence sufficiency scores below configured threshold.
        """
        if not self._enabled or status != "completed":
            return False

        if not answer or not answer.strip():
            return False

        # Refusal & low-context markers
        refusal_markers = (
            "i do not have enough evidence",
            "i don't have enough evidence",
            "not enough evidence",
            "no relevant context",
            "cannot answer based on the provided documents",
            "no relevant documents",
            "unable to find any information",
        )
        lower_ans = answer.lower()
        if any(marker in lower_ans for marker in refusal_markers):
            logger.info(
                "RAG cache skipped: Answer contains refusal / insufficient evidence marker."
            )
            return False

        # Agent checks (exclude live web searches from persistent cache)
        if agent_diagnostics:
            if isinstance(agent_diagnostics, dict):
                agents_executed = agent_diagnostics.get("executed_agents", [])
                if any("web" in str(a).lower() for a in agents_executed):
                    logger.info(
                        "RAG cache skipped: Execution plan contains WebSearchAgent."
                    )
                    return False
                evidence_score = agent_diagnostics.get("evidence_score")
                if (
                    evidence_score is not None
                    and float(evidence_score) < self._min_confidence
                ):
                    logger.info(
                        f"RAG cache skipped: Evidence score {evidence_score} < {self._min_confidence}"
                    )
                    return False

        return True

    async def replay_stream_events(
        self,
        cached_payload: dict[str, Any],
        assistant_message_id: UUID,
        conversation_id: UUID | None,
        delay_ms: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yields paced SSE events from the cached payload matching the exact protocol
        emitted during a live LLM streaming session.
        """
        effective_delay = delay_ms if delay_ms is not None else self._stream_delay_ms
        citations = cached_payload.get("citations", [])
        answer_text = cached_payload.get("answer", "")
        diag = cached_payload.get("diagnostics") or {}
        usage = cached_payload.get("usage") or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        # 1. Initial metadata event
        yield {
            "event": "metadata",
            "data": {
                "citations": citations,
                "retrieval_time_ms": 0.0,
                "conversation_id": str(conversation_id) if conversation_id else "",
                "diagnostics": {
                    **diag,
                    "cache_hit": True,
                },
            },
        }

        # 2. Replay text in paced word chunks
        if answer_text:
            words = answer_text.split(" ")
            chunk_word_size = 4
            for i in range(0, len(words), chunk_word_size):
                chunk_str = " ".join(words[i : i + chunk_word_size])
                if i + chunk_word_size < len(words):
                    chunk_str += " "
                yield {
                    "event": "text",
                    "data": {"text": chunk_str},
                }
                if effective_delay > 0:
                    await asyncio.sleep(effective_delay / 1000.0)

        # 3. Yield synthesis citations event
        yield {
            "event": "synthesis_done",
            "data": {
                "usage": usage,
                "citations": citations,
            },
        }

        # 4. Final done event
        yield {
            "event": "done",
            "data": {
                "assistant_message_id": str(assistant_message_id),
                "conversation_id": str(conversation_id) if conversation_id else "",
                "total_time_ms": round(
                    effective_delay * max(1, len(answer_text.split()) // 4), 2
                ),
                "citations": citations,
                "answer": answer_text,
                "diagnostics": {
                    **diag,
                    "cache_hit": True,
                },
                "usage": usage,
            },
        }
