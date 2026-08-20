import asyncio
import logging
import time
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.chat.domain.models import ChatMessage, MessageRole
from app.documents.domain.interfaces import DenseRetriever, EmbeddingGenerator
from app.documents.domain.models import DocumentRetrievalScope, RetrievedChunk

logger = logging.getLogger(__name__)


class HypotheticalDocument(BaseModel):
    """
    Structured representation of a HyDE-generated hypothetical document.
    HyDE text is ONLY used to generate a dense semantic retrieval vector.
    It is NEVER treated as real evidence, a ground truth source, or a citation.
    """

    query: str
    hypothetical_text: str
    embedding: list[float] | None = None
    provider: str = "deterministic"
    token_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(frozen=True)


class HyDEGenerator(Protocol):
    """Protocol for HyDE hypothetical document generation."""

    async def generate(self, query: str) -> HypotheticalDocument: ...


class DeterministicHyDEGenerator:
    """
    Lightweight, fast, deterministic heuristic HyDE generator for testing and fast profiles.
    IMPORTANT: This is strictly for pipeline plumbing and testing.
    Real semantic HyDE evaluation requires an LLM-backed generator.
    """

    _DOMAIN_TEMPLATES: list[tuple[list[str], str]] = [
        (
            ["sla", "slo", "availability", "uptime", "tier"],
            "The standard service level agreement defines availability Service Level Objectives (SLOs) "
            "for enterprise and standard tier tenants with specific uptime commitments, maintenance windows, "
            "and service credit policies governed by platform engineering standards.",
        ),
        (
            ["encryption", "kms", "cmk", "aes", "at rest", "key rotation"],
            "Data at rest is secured using AES-256-GCM encryption with Customer Managed Keys (CMK) "
            "managed in AWS KMS. Automated cryptographic key rotation is scheduled and enforced on a 365-day cycle.",
        ),
        (
            ["revenue", "financial", "gaap", "fy2025", "ebitda", "churn", "growth"],
            "The financial summary outlines consolidated GAAP revenue, annual recurring revenue (ARR), "
            "year-over-year revenue growth percentages, operating margins, customer churn metrics, and fiscal performance targets.",
        ),
        (
            [
                "jwt",
                "token",
                "auth",
                "authentication",
                "refresh token",
                "access token",
                "oauth",
            ],
            "The authentication protocol issues short-lived JSON Web Token (JWT) access tokens and "
            "longer-lived refresh tokens stored securely in HTTP-only cookies with HMAC SHA-256 signing.",
        ),
        (
            [
                "architecture",
                "protect",
                "customer data",
                "security",
                "isolation",
                "multi-tenant",
            ],
            "The multi-tenant cloud architecture protects customer data through row-level security (RLS), "
            "strict tenant isolation, encrypted storage volumes, zero-trust network policies, and role-based access control.",
        ),
    ]

    async def generate(self, query: str) -> HypotheticalDocument:
        cleaned_query = query.strip()
        q_lower = cleaned_query.lower()

        matched_passage: str | None = None
        for keywords, passage in self._DOMAIN_TEMPLATES:
            if any(kw in q_lower for kw in keywords):
                matched_passage = (
                    f"In response to the inquiry regarding '{cleaned_query}': {passage}"
                )
                break

        if not matched_passage:
            matched_passage = (
                f"This document provides comprehensive technical documentation and authoritative details "
                f"regarding: {cleaned_query}. It explains the core operational principles, configurations, "
                f"specifications, and standards applied within the system."
            )

        token_estimate = max(1, len(matched_passage) // 4)
        return HypotheticalDocument(
            query=cleaned_query,
            hypothetical_text=matched_passage,
            embedding=None,
            provider="deterministic",
            token_count=token_estimate,
        )


class LLMHyDEGenerator:
    """
    LLM-backed HyDE generator with strict timeout, token capping, retry policy, and fallback.
    """

    def __init__(
        self,
        llm_generation_service: Any,
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.0,
        max_tokens: int = 512,
        timeout_ms: int = 1000,
        max_retries: int = 1,
        fallback_generator: HyDEGenerator | None = None,
    ) -> None:
        self._llm = llm_generation_service
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_sec = max(0.1, timeout_ms / 1000.0)
        self._max_retries = max_retries
        self._fallback_generator = fallback_generator or DeterministicHyDEGenerator()

    async def generate(self, query: str) -> HypotheticalDocument:
        cleaned_query = query.strip()
        system_instruction = (
            "You are a specialized technical document retrieval assistant. "
            "Given a user search query, write a concise, hypothetical technical passage (1-2 paragraphs) "
            "that directly answers the question using domain-specific technical terminology. "
            "Do not include conversational filler, greetings, or meta-commentary."
        )

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_instruction),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Write a hypothetical document passage answering: {cleaned_query}",
            ),
        ]

        for attempt in range(self._max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._llm.generate(
                        messages=messages,
                        model=self._model,
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    ),
                    timeout=self._timeout_sec,
                )
                hypo_text = (
                    response.content.strip()
                    if hasattr(response, "content")
                    else str(response).strip()
                )
                if hypo_text:
                    token_count = len(hypo_text) // 4
                    if hasattr(response, "usage") and response.usage:
                        token_count = getattr(
                            response.usage,
                            "completion_tokens",
                            getattr(response.usage, "output_tokens", token_count),
                        )
                    return HypotheticalDocument(
                        query=cleaned_query,
                        hypothetical_text=hypo_text,
                        embedding=None,
                        provider="llm",
                        token_count=token_count,
                    )
            except TimeoutError:
                logger.warning(
                    f"HyDE LLM generation timed out after {self._timeout_sec:.2f}s (attempt {attempt + 1}/{self._max_retries + 1})"
                )
            except Exception as e:
                logger.warning(
                    f"HyDE LLM generation failed: {e} (attempt {attempt + 1}/{self._max_retries + 1})"
                )

        logger.info("HyDE LLM generator falling back to deterministic generator.")
        return await self._fallback_generator.generate(cleaned_query)


class SafeHyDEExecutor:
    """
    Safe HyDE retrieval executor.
    Executes HyDE semantic vector search while ensuring that:
    1. HyDE failures fall back safely to standard dense query retrieval.
    2. HyDE generated text is NEVER exposed as evidence or citations.
    3. Only real document chunks from authorized scope are returned.
    """

    def __init__(
        self,
        hyde_generator: HyDEGenerator,
        embedding_generator: EmbeddingGenerator,
        dense_retriever: DenseRetriever,
        timeout_ms: int = 1000,
    ) -> None:
        self._hyde_generator = hyde_generator
        self._embedding_generator = embedding_generator
        self._dense_retriever = dense_retriever
        self._timeout_sec = max(0.1, timeout_ms / 1000.0)

    async def execute_hyde_dense_retrieval(
        self,
        query: str,
        user_id: Any,
        top_k: int,
        document_ids: list[Any] | None = None,
        tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
        retrieval_scope: DocumentRetrievalScope | None = None,
    ) -> tuple[list[RetrievedChunk], HypotheticalDocument | None, float]:
        """
        Executes HyDE dense retrieval:
        1. Generate hypothetical document.
        2. Embed hypothetical text.
        3. Retrieve real chunks from vector store using the hypothetical embedding.
        Returns: (real_retrieved_chunks, hypothetical_doc, hyde_latency_sec)
        """
        start_time = time.perf_counter()
        hypo_doc: HypotheticalDocument | None = None

        try:
            # 1. Generate hypothetical passage with strict timeout
            hypo_doc = await asyncio.wait_for(
                self._hyde_generator.generate(query),
                timeout=self._timeout_sec,
            )

            # 2. Retrieve real chunks from Qdrant using hypothetical passage
            real_chunks = await self._dense_retriever.retrieve(
                query=hypo_doc.hypothetical_text,
                user_id=user_id,
                top_k=top_k,
                document_ids=document_ids,
                tags=tags,
                filter_metadata=filter_metadata,
                retrieval_scope=retrieval_scope,
            )

            latency = time.perf_counter() - start_time
            logger.info(
                f"HyDE dense retrieval successful: generated {hypo_doc.token_count} tokens in {latency:.4f}s, retrieved {len(real_chunks)} chunks."
            )
            return real_chunks, hypo_doc, latency

        except Exception as e:
            logger.warning(
                f"HyDE dense retrieval encountered error or timeout ({e}). Falling back to standard dense retrieval."
            )
            # Safe Fallback to standard dense retrieval using original query
            fallback_chunks = await self._dense_retriever.retrieve(
                query=query,
                user_id=user_id,
                top_k=top_k,
                document_ids=document_ids,
                tags=tags,
                filter_metadata=filter_metadata,
                retrieval_scope=retrieval_scope,
            )
            latency = time.perf_counter() - start_time
            return fallback_chunks, hypo_doc, latency
