import asyncio
import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class QueryExpander(Protocol):
    async def expand(
        self,
        query: str,
        context: Any | None = None,
        max_queries: int = 3,
    ) -> list[str]: ...


class LexicalQueryExpander(QueryExpander):
    """
    High-precision deterministic lexical query expander.
    Uses technical synonyms, normalized aliases, and acronym mapping
    without external LLM calls or latency overhead.
    """

    # Domain vocabulary & synonym lookup map
    SYNONYM_MAP: dict[str, list[str]] = {
        "jwt": ["json web token", "jwt token authentication"],
        "oauth": ["oauth 2.0 authorization", "oauth token exchange"],
        "rag": ["retrieval-augmented generation", "document retrieval search"],
        "llm": ["large language model", "generative ai model"],
        "sla": ["service level agreement", "uptime reliability target"],
        "latency": ["response time", "execution delay"],
        "db": ["database", "persistence storage"],
        "auth": ["authentication and authorization", "access control"],
        "expiry": ["expiration lifetime", "validity duration"],
        "expiration": ["expiry time", "validity lifetime"],
        "vector": ["embedding representation", "semantic dense vector"],
        "bm25": ["sparse keyword search", "lexical inverted index"],
        "qdrant": ["vector store database", "qdrant index"],
        "rerank": ["cross-encoder reranking", "re-ranking relevance"],
        "reranker": ["cross-encoder reranker", "re-ranking model"],
        "revenue": ["financial turnover", "annual sales revenue"],
        "churn": ["customer turnover rate", "attrition rate"],
        "metric": ["performance indicator", "measurement metric"],
        "metrics": ["performance indicators", "evaluation measurements"],
    }

    def __init__(self, custom_synonyms: dict[str, list[str]] | None = None):
        self.synonym_map = {k.lower(): v for k, v in self.SYNONYM_MAP.items()}
        if custom_synonyms:
            for k, v in custom_synonyms.items():
                self.synonym_map[k.lower()] = [x.lower() for x in v]

    async def expand(
        self,
        query: str,
        context: Any | None = None,
        max_queries: int = 3,
    ) -> list[str]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return [query]

        # The original query MUST always be element 0
        expanded_queries = [cleaned_query]
        if max_queries <= 1:
            return expanded_queries

        lower_query = cleaned_query.lower()
        words = re.findall(r"\b\w+\b", lower_query)

        derived_candidates: list[str] = []

        # 1. Full phrase substitution for matched keywords
        for keyword, replacements in self.synonym_map.items():
            if re.search(rf"\b{re.escape(keyword)}\b", lower_query):
                for repl in replacements:
                    candidate = re.sub(
                        rf"\b{re.escape(keyword)}\b",
                        repl,
                        lower_query,
                        flags=re.IGNORECASE,
                    )
                    candidate_clean = " ".join(candidate.split())
                    if candidate_clean and candidate_clean.lower() != lower_query:
                        derived_candidates.append(candidate_clean)

        # 2. Key entity-focused variant if query contains multiple domain terms
        matched_terms = [w for w in words if w in self.synonym_map]
        if len(matched_terms) >= 2:
            expanded_phrase = lower_query
            for term in matched_terms:
                repl = self.synonym_map[term][0]
                expanded_phrase = re.sub(
                    rf"\b{re.escape(term)}\b",
                    repl,
                    expanded_phrase,
                    flags=re.IGNORECASE,
                )
            expanded_phrase_clean = " ".join(expanded_phrase.split())
            if expanded_phrase_clean.lower() != lower_query:
                derived_candidates.append(expanded_phrase_clean)

        # Deduplicate derived candidates while preserving order
        seen_lower = {cleaned_query.lower()}
        for cand in derived_candidates:
            cand_lower = cand.lower()
            if cand_lower not in seen_lower:
                seen_lower.add(cand_lower)
                expanded_queries.append(cand)
                if len(expanded_queries) >= max_queries:
                    break

        return expanded_queries


class SafeQueryExpander(QueryExpander):
    """
    Composite query expander wrapping underlying expander with
    strict timeout enforcement, output bounding, and graceful fallback.
    """

    def __init__(
        self,
        expander: QueryExpander | None = None,
        timeout_ms: int = 500,
        max_queries: int = 3,
    ):
        self._expander = expander or LexicalQueryExpander()
        self._timeout_ms = timeout_ms
        self._max_queries = max_queries

    async def expand(
        self,
        query: str,
        context: Any | None = None,
        max_queries: int | None = None,
    ) -> list[str]:
        effective_max = max_queries if max_queries is not None else self._max_queries
        timeout_sec = self._timeout_ms / 1000.0

        try:
            expanded = await asyncio.wait_for(
                self._expander.expand(query, context, max_queries=effective_max),
                timeout=timeout_sec,
            )
            # Guarantee original query is preserved at index 0
            cleaned_original = query.strip()
            if not expanded:
                return [cleaned_original]
            if expanded[0].strip().lower() != cleaned_original.lower():
                expanded = [cleaned_original] + [
                    q for q in expanded if q.strip().lower() != cleaned_original.lower()
                ]
            return expanded[:effective_max]
        except TimeoutError:
            logger.warning(
                f"Query expansion timed out after {self._timeout_ms}ms; falling back to original query."
            )
            return [query.strip()]
        except Exception as e:
            logger.warning(
                f"Query expansion failed with error ({e}); falling back to original query."
            )
            return [query.strip()]
