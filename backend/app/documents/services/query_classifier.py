import logging
import re
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    FACTUAL = "FACTUAL"
    EXPLANATION = "EXPLANATION"
    COMPARISON = "COMPARISON"
    MULTI_HOP = "MULTI_HOP"
    MULTI_DOCUMENT = "MULTI_DOCUMENT"
    AMBIGUOUS = "AMBIGUOUS"
    CONVERSATIONAL = "CONVERSATIONAL"
    NUMERICAL = "NUMERICAL"
    TABLE = "TABLE"
    MULTIMODAL = "MULTIMODAL"
    GRAPH = "GRAPH"


class QueryClassification(BaseModel):
    query_type: QueryType
    confidence: float = Field(ge=0.0, le=1.0)
    requires_expansion: bool = False
    requires_decomposition: bool = False
    recommended_top_k: int = 10
    reasons: list[str] = Field(default_factory=list)
    has_multiple_evidence_targets: bool = False

    model_config = ConfigDict(frozen=True)


class QueryClassifier(Protocol):
    def classify(self, query: str) -> QueryClassification: ...


class DeterministicQueryClassifier(QueryClassifier):
    """
    Lightweight, fast, deterministic heuristic query classifier.
    Operates in sub-millisecond time without external LLM dependencies.
    """

    _GREETINGS = {
        "hello",
        "hi",
        "hey",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "who are you",
        "what can you do",
        "how are you",
        "help",
    }

    _CONVERSATIONAL_PREFIXES = {
        "hello",
        "hi",
        "hey",
        "greetings",
    }

    _COMPARISON_PATTERNS = [
        re.compile(r"\bcompare\b", re.IGNORECASE),
        re.compile(r"\bversus\b|\bvs\.?\b", re.IGNORECASE),
        re.compile(r"\bdifference\s+(between|in)\b", re.IGNORECASE),
        re.compile(
            r"\b(pros\s+and\s+cons|advantages\s+and\s+disadvantages)\b", re.IGNORECASE
        ),
        re.compile(r"\bhow\s+does\s+.+\s+differ\s+from\b", re.IGNORECASE),
        re.compile(r"\bwhich\s+is\s+better\b", re.IGNORECASE),
    ]

    _MULTI_HOP_PATTERNS = [
        re.compile(
            r"\b(and\s+also|as\s+well\s+as|along\s+with|in\s+addition\s+to)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(what\s+is\s+the\s+.+\s+of\s+the\s+.+\s+that|after\s+.+\s+what\s+was)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(who\s+(is|was)\s+the\s+.+\s+of\s+the\s+.+\s+who)\b", re.IGNORECASE
        ),
        re.compile(r"\b(both\s+.+\s+and\s+.+\s+and\s+.+)\b", re.IGNORECASE),
        re.compile(r"\?.+\?", re.IGNORECASE),  # multiple questions
    ]

    _MULTI_DOCUMENT_PATTERNS = [
        re.compile(
            r"\b(across\s+(the\s+|all\s+)?documents|across\s+(both|all)\s+reports)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(in\s+both\s+documents|in\s+document\s+\w+\s+and\s+document\s+\w+)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(compare\s+the\s+two\s+files|cross-reference)\b", re.IGNORECASE),
    ]

    _NUMERICAL_PATTERNS = [
        re.compile(
            r"\b(how\s+many|how\s+much|what\s+percentage|what\s+proportion)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(revenue|growth\s+rate|sla\s+target|metrics?|statistics?|total|average|sum)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(q[1-4]\s+20\d\d|20\d\d\s+q[1-4]|fy\s*20\d\d|\$\d+|\d+\%)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(calculate|count|sum\s+of|highest|lowest|maximum|minimum)\b",
            re.IGNORECASE,
        ),
    ]

    _EXPLANATION_PATTERNS = [
        re.compile(r"\b(why\s+(is|are|does|do|did|was|were))\b", re.IGNORECASE),
        re.compile(r"\b(how\s+(does|do|did|can|could|to))\b", re.IGNORECASE),
        re.compile(
            r"\b(explain|describe\s+how|walk\s+through|what\s+causes|reason\s+for)\b",
            re.IGNORECASE,
        ),
    ]

    _TABLE_PATTERNS = [
        re.compile(
            r"\b(in\s+the\s+table|table\s+\d+|from\s+the\s+table|tabular|spreadsheet|csv|column|row\s+\d+|row-by-row)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(balance\s+sheet|income\s+statement|financial\s+table)\b", re.IGNORECASE
        ),
    ]

    _MULTIMODAL_PATTERNS = [
        re.compile(
            r"\b(in\s+the\s+image|in\s+the\s+figure|figure\s+\d+|chart|diagram|plot|graph\s+showing|bar\s+chart|pie\s+chart|trend\s+line|axes|axis)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(visual|illustration|photo|screenshot|architecture\s+diagram)\b",
            re.IGNORECASE,
        ),
    ]

    _GRAPH_PATTERNS = [
        re.compile(
            r"\b(relationship\s+between|connected\s+to|network\s+of|who\s+works\s+for|subsidiary\s+of|parent\s+company)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(affiliated\s+with|acquired\s+by|entities\s+related\s+to|knowledge\s+graph|organization\s+structure)\b",
            re.IGNORECASE,
        ),
    ]

    _AMBIGUOUS_VAGUE_TERMS = {
        "it",
        "that",
        "this",
        "thing",
        "stuff",
        "info",
        "details",
        "more",
        "system",
        "specs",
        "docs",
        "status",
        "overview",
        "tell me",
        "show me",
    }

    def classify(self, query: str) -> QueryClassification:
        normalized = query.strip()
        lower = normalized.lower()
        words = re.findall(r"\b\w+\b", lower)
        word_count = len(words)

        # 0a. Table Check
        for pattern in self._TABLE_PATTERNS:
            if pattern.search(lower):
                return QueryClassification(
                    query_type=QueryType.TABLE,
                    confidence=0.92,
                    requires_expansion=False,
                    requires_decomposition=False,
                    recommended_top_k=10,
                    reasons=["Matched tabular/structured data query pattern"],
                )

        # 0b. Multimodal / Visual Check
        for pattern in self._MULTIMODAL_PATTERNS:
            if pattern.search(lower):
                return QueryClassification(
                    query_type=QueryType.MULTIMODAL,
                    confidence=0.90,
                    requires_expansion=False,
                    requires_decomposition=False,
                    recommended_top_k=10,
                    reasons=["Matched visual/image/chart element pattern"],
                )

        # 0c. Graph / Entity Network Check
        for pattern in self._GRAPH_PATTERNS:
            if pattern.search(lower):
                return QueryClassification(
                    query_type=QueryType.GRAPH,
                    confidence=0.91,
                    requires_expansion=True,
                    requires_decomposition=False,
                    recommended_top_k=15,
                    reasons=["Matched entity relationship / knowledge graph pattern"],
                )

        # 1. Conversational Check (pure greetings, salutations, casual status check)
        is_pure_greeting = (
            lower in self._GREETINGS
            or (
                word_count <= 4
                and any(g in lower for g in ("how are you", "what's up", "who are you", "what can you do"))
            )
            or (word_count <= 3 and any(w in self._GREETINGS for w in words))
            or (word_count <= 2 and words and words[0] in self._CONVERSATIONAL_PREFIXES)
        )
        if is_pure_greeting:
            return QueryClassification(
                query_type=QueryType.CONVERSATIONAL,
                confidence=0.95,
                requires_expansion=False,
                requires_decomposition=False,
                recommended_top_k=5,
                reasons=["Matched conversational greeting or salutation pattern"],
            )

        # For queries with leading greetings (e.g. "hello, can you compare..."), strip greeting prefix for pattern matching
        clean_lower = re.sub(
            r"^(?:hello|hi|hey|greetings|dear|good\s+(?:morning|afternoon|evening))\b[\s,:-]*",
            "",
            lower,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_lower:
            clean_lower = lower

        # 2. Multi-Document Check
        for pattern in self._MULTI_DOCUMENT_PATTERNS:
            if pattern.search(lower) or pattern.search(clean_lower):
                return QueryClassification(
                    query_type=QueryType.MULTI_DOCUMENT,
                    confidence=0.90,
                    requires_expansion=True,
                    requires_decomposition=True,
                    recommended_top_k=20,
                    reasons=["Matched multi-document cross-referencing intent"],
                    has_multiple_evidence_targets=True,
                )

        # 3. Multi-Hop Check
        for pattern in self._MULTI_HOP_PATTERNS:
            if pattern.search(lower) or pattern.search(clean_lower):
                return QueryClassification(
                    query_type=QueryType.MULTI_HOP,
                    confidence=0.88,
                    requires_expansion=True,
                    requires_decomposition=True,
                    recommended_top_k=20,
                    reasons=["Matched multi-hop / multi-part conjunct structure"],
                    has_multiple_evidence_targets=True,
                )

        # 4. Comparison Check
        for pattern in self._COMPARISON_PATTERNS:
            if pattern.search(lower) or pattern.search(clean_lower):
                # Conservative check: is this a multi-target comparison or a simple single comparison?
                # Multi-target indicator: contains multiple independent aspects or conjuncts
                has_multi_targets = bool(
                    re.search(
                        r"\b(as\s+well\s+as|and\s+also|along\s+with|across\s+both)\b",
                        lower,
                    )
                    or (len(re.findall(r"\band\b", lower)) >= 2)
                )
                return QueryClassification(
                    query_type=QueryType.COMPARISON,
                    confidence=0.85,
                    requires_expansion=False,
                    requires_decomposition=has_multi_targets,
                    recommended_top_k=15 if has_multi_targets else 12,
                    reasons=[
                        f"Matched comparison intent (multi_targets={has_multi_targets})"
                    ],
                    has_multiple_evidence_targets=has_multi_targets,
                )

        # 5. Numerical Check
        numerical_hits = sum(
            1 for p in self._NUMERICAL_PATTERNS if (p.search(lower) or p.search(clean_lower))
        )
        if numerical_hits >= 1:
            # Check if it has multiple sub-questions
            if " and " in lower and word_count > 8:
                return QueryClassification(
                    query_type=QueryType.MULTI_HOP,
                    confidence=0.82,
                    requires_expansion=True,
                    requires_decomposition=True,
                    recommended_top_k=20,
                    reasons=["Matched multi-period/multi-metric numerical query"],
                    has_multiple_evidence_targets=True,
                )
            return QueryClassification(
                query_type=QueryType.NUMERICAL,
                confidence=0.85,
                requires_expansion=False,
                requires_decomposition=False,
                recommended_top_k=10,
                reasons=["Matched numerical/quantitative pattern"],
            )

        # 6. Ambiguous Check
        # Short queries without clear technical anchors
        if word_count <= 2 or (
            word_count <= 3
            and all(w in self._AMBIGUOUS_VAGUE_TERMS or len(w) <= 2 for w in words)
        ):
            return QueryClassification(
                query_type=QueryType.AMBIGUOUS,
                confidence=0.80,
                requires_expansion=True,
                requires_decomposition=False,
                recommended_top_k=15,
                reasons=[
                    "Short query lacking specific entity anchors; requires lexical expansion"
                ],
            )

        # 7. Explanation Check
        for pattern in self._EXPLANATION_PATTERNS:
            if pattern.search(lower) or pattern.search(clean_lower):
                return QueryClassification(
                    query_type=QueryType.EXPLANATION,
                    confidence=0.85,
                    requires_expansion=True,
                    requires_decomposition=False,
                    recommended_top_k=12,
                    reasons=["Matched explanatory / mechanism question pattern"],
                )

        # 8. Factual (Default)
        return QueryClassification(
            query_type=QueryType.FACTUAL,
            confidence=0.90,
            requires_expansion=False,
            requires_decomposition=False,
            recommended_top_k=10,
            reasons=["Standard factual query"],
        )
