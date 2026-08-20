import asyncio
import logging
import re
import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.documents.services.query_classifier import QueryType

logger = logging.getLogger(__name__)


class QuerySubtask(BaseModel):
    id: str
    query: str
    parent_query: str
    required_evidence: str | None = None

    model_config = ConfigDict(frozen=True)


class QueryDecomposer(Protocol):
    async def decompose(
        self,
        query: str,
        query_type: QueryType | None = None,
        max_subtasks: int = 3,
    ) -> list[QuerySubtask]: ...


class DeterministicQueryDecomposer(QueryDecomposer):
    """
    Conservative, deterministic query decomposer for complex multi-hop / multi-document questions.
    Follows strict guidelines:
    - MULTI_HOP / MULTI_DOCUMENT: decomposes compound conjunctions into bounded subtasks.
    - COMPARISON: decomposes ONLY when multiple independent evidence targets are present.
    - Simple comparisons and factual queries remain a single query.
    """

    _CONJUNCT_SPLIT_PATTERNS = [
        re.compile(r"\s+and\s+also\s+", re.IGNORECASE),
        re.compile(r"\s+as\s+well\s+as\s+", re.IGNORECASE),
        re.compile(r"\s+along\s+with\s+", re.IGNORECASE),
        re.compile(r"\s+in\s+addition\s+to\s+", re.IGNORECASE),
    ]

    _QUESTION_SPLIT_PATTERN = re.compile(r"\?\s*", re.IGNORECASE)

    async def decompose(
        self,
        query: str,
        query_type: QueryType | None = None,
        max_subtasks: int = 3,
    ) -> list[QuerySubtask]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        parent_id = str(uuid.uuid4())[:8]

        # Default: single subtask containing the original query
        default_subtask = QuerySubtask(
            id=f"{parent_id}-0",
            query=cleaned_query,
            parent_query=cleaned_query,
            required_evidence=None,
        )

        # Only decompose if query_type warrants decomposition
        if query_type not in (
            QueryType.MULTI_HOP,
            QueryType.MULTI_DOCUMENT,
            QueryType.COMPARISON,
        ):
            return [default_subtask]

        # For comparison queries, verify if multiple distinct evidence targets exist
        if query_type == QueryType.COMPARISON:
            lower = cleaned_query.lower()
            # Simple comparisons like "Compare X and Y" stay as single query
            is_multi_target = bool(
                re.search(
                    r"\b(as\s+well\s+as|and\s+also|along\s+with|across\s+both)\b",
                    lower,
                )
                or (len(re.findall(r"\band\b", lower)) >= 2)
            )
            if not is_multi_target:
                return [default_subtask]

        sub_queries: list[str] = []

        # 1. Check for multiple distinct questions separated by '?'
        if "?" in cleaned_query:
            parts = [
                p.strip()
                for p in self._QUESTION_SPLIT_PATTERN.split(cleaned_query)
                if p.strip()
            ]
            if len(parts) >= 2:
                for part in parts:
                    sub_q = part if part.endswith("?") else f"{part}?"
                    if len(sub_q.split()) >= 3:
                        sub_queries.append(sub_q)

        # 2. Check for explicit conjunct splitters ("and also", "as well as", etc.)
        if not sub_queries:
            for pattern in self._CONJUNCT_SPLIT_PATTERNS:
                splits = pattern.split(cleaned_query)
                if len(splits) >= 2:
                    for s in splits:
                        clean_s = s.strip().rstrip("?,.")
                        if len(clean_s.split()) >= 2:
                            sub_queries.append(clean_s)
                    break

        # 3. Check for compound "What were X and Y?" or "X and the Y target"
        if not sub_queries and " and " in cleaned_query.lower():
            # e.g., "What were 2025 revenue growth and the engineering SLA target?"
            match = re.match(
                r"^(what\s+(were|are|is)\s+)(.+)\s+and\s+(.+)$",
                cleaned_query,
                re.IGNORECASE,
            )
            if match:
                prefix = match.group(1).strip()
                part1 = match.group(3).strip().rstrip("?,.")
                part2 = match.group(4).strip().rstrip("?,.")
                if len(part1.split()) >= 2 and len(part2.split()) >= 2:
                    sub_queries.append(f"{prefix} {part1}")
                    sub_queries.append(f"{prefix} {part2}")

        # If no valid decomposition was produced, return single original query
        if not sub_queries:
            return [default_subtask]

        # Deduplicate and bound subtasks
        seen_lower = set()
        subtasks: list[QuerySubtask] = []
        for _i, sq in enumerate(sub_queries):
            sq_clean = " ".join(sq.split()).strip()
            sq_lower = sq_clean.lower()
            if sq_lower not in seen_lower and len(sq_clean.split()) >= 2:
                seen_lower.add(sq_lower)
                subtasks.append(
                    QuerySubtask(
                        id=f"{parent_id}-{len(subtasks)}",
                        query=sq_clean,
                        parent_query=cleaned_query,
                        required_evidence=f"Evidence for: {sq_clean}",
                    )
                )
                if len(subtasks) >= max_subtasks:
                    break

        return subtasks if subtasks else [default_subtask]


class SafeQueryDecomposer(QueryDecomposer):
    """
    Safe wrapper enforcing timeouts and fallback to single original query.
    """

    def __init__(
        self,
        decomposer: QueryDecomposer | None = None,
        timeout_ms: int = 500,
        max_subtasks: int = 3,
    ):
        self._decomposer = decomposer or DeterministicQueryDecomposer()
        self._timeout_ms = timeout_ms
        self._max_subtasks = max_subtasks

    async def decompose(
        self,
        query: str,
        query_type: QueryType | None = None,
        max_subtasks: int | None = None,
    ) -> list[QuerySubtask]:
        effective_max = max_subtasks if max_subtasks is not None else self._max_subtasks
        timeout_sec = self._timeout_ms / 1000.0

        try:
            subtasks = await asyncio.wait_for(
                self._decomposer.decompose(
                    query, query_type, max_subtasks=effective_max
                ),
                timeout=timeout_sec,
            )
            return (
                subtasks[:effective_max]
                if subtasks
                else [
                    QuerySubtask(
                        id=f"fallback-{uuid.uuid4().hex[:6]}",
                        query=query.strip(),
                        parent_query=query.strip(),
                    )
                ]
            )
        except TimeoutError:
            logger.warning(
                f"Query decomposition timed out after {self._timeout_ms}ms; falling back to original query."
            )
            return [
                QuerySubtask(
                    id=f"fallback-{uuid.uuid4().hex[:6]}",
                    query=query.strip(),
                    parent_query=query.strip(),
                )
            ]
        except Exception as e:
            logger.warning(
                f"Query decomposition failed with error ({e}); falling back to original query."
            )
            return [
                QuerySubtask(
                    id=f"fallback-{uuid.uuid4().hex[:6]}",
                    query=query.strip(),
                    parent_query=query.strip(),
                )
            ]
