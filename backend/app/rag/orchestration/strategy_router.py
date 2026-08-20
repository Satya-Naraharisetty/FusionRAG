import logging
import re
from typing import Any

from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryClassifier,
    QueryType,
)
from app.rag.orchestration.models import RetrievalDecision, RetrievalStrategy

logger = logging.getLogger(__name__)


class RetrievalStrategyRouter:
    """
    Deterministic Adaptive Retrieval Strategy Router.
    Evaluates queries against strict precedence rules and returns structured reasoning signals
    without exposing private prompts or chain-of-thought.
    """

    def __init__(self, query_classifier: QueryClassifier | None = None) -> None:
        self._classifier = query_classifier or DeterministicQueryClassifier()

    _ACRONYM_PATTERN = re.compile(
        r"\b(CMK|KMS|JWT|AES|GCM|SLO|SLA|SEV|EBITDA|ARR|GAAP|CIDR|VPC|IAM|RBAC|RLS)\b",
        re.IGNORECASE,
    )
    _CONCEPTUAL_PATTERNS = [
        re.compile(
            r"\b(how\s+does\s+.+\s+protect\b|how\s+does\s+.+\s+work\b)", re.IGNORECASE
        ),
        re.compile(
            r"\b(principles\s+of|overview\s+of|architecture\s+of|philosophy\s+of)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(why\s+does|explain\s+how|describe\s+the\s+mechanism)\b", re.IGNORECASE
        ),
        re.compile(
            r"\b(best\s+practices\s+for|guidelines\s+governing)\b", re.IGNORECASE
        ),
    ]

    async def select_strategy(
        self,
        query: str,
        classification: QueryClassification | None = None,
        history: Any | None = None,
        resource_budget: dict[str, Any] | None = None,
    ) -> RetrievalDecision:
        cleaned_query = query.strip()
        if not cleaned_query:
            return RetrievalDecision(
                strategy=RetrievalStrategy.STANDARD_HYBRID,
                confidence=1.0,
                reasoning_signals=["empty_query_fallback"],
                expected_evidence_targets=[],
                max_iterations=1,
                max_retrieval_calls=1,
            )

        if classification is None:
            classification = self._classifier.classify(cleaned_query)

        reasoning_signals: list[str] = []
        expected_targets = self._extract_evidence_targets(cleaned_query, classification)

        # 0. Hard Resource Budget Constraints
        if resource_budget and resource_budget.get("max_allowed_calls", 99) <= 1:
            reasoning_signals.append("hard_resource_budget_constraint")
            return RetrievalDecision(
                strategy=RetrievalStrategy.STANDARD_HYBRID,
                confidence=0.95,
                reasoning_signals=reasoning_signals,
                expected_evidence_targets=expected_targets,
                max_iterations=1,
                max_retrieval_calls=1,
            )

        # Precedence Rule Evaluation:

        # 1. Multi-hop / Multi-target requirements -> DECOMPOSITION
        is_multi_hop = (
            classification.query_type
            in (
                QueryType.MULTI_HOP,
                QueryType.MULTI_DOCUMENT,
                QueryType.COMPARISON,
            )
            or classification.requires_decomposition
            or classification.has_multiple_evidence_targets
        )
        if is_multi_hop:
            reasoning_signals.append("multi_hop_detected")
            if classification.has_multiple_evidence_targets:
                reasoning_signals.append("multiple_evidence_targets")
            return RetrievalDecision(
                strategy=RetrievalStrategy.DECOMPOSITION,
                confidence=classification.confidence,
                reasoning_signals=reasoning_signals,
                expected_evidence_targets=expected_targets,
                max_iterations=2,
                max_retrieval_calls=min(4, len(expected_targets) + 1),
            )

        # 2. Vocabulary mismatch / Acronym-heavy query -> QUERY_EXPANSION
        has_acronyms = bool(self._ACRONYM_PATTERN.search(cleaned_query))
        is_vocab_mismatch = has_acronyms or (
            classification.requires_expansion
            and classification.query_type != QueryType.EXPLANATION
        )
        if is_vocab_mismatch:
            if has_acronyms:
                reasoning_signals.append("acronym_detected")
            reasoning_signals.append("vocabulary_mismatch_detected")
            return RetrievalDecision(
                strategy=RetrievalStrategy.QUERY_EXPANSION,
                confidence=max(0.85, classification.confidence),
                reasoning_signals=reasoning_signals,
                expected_evidence_targets=expected_targets,
                max_iterations=1,
                max_retrieval_calls=2,
            )

        # 3. Conceptual / Semantic / Paraphrased question -> HYDE
        is_conceptual = any(
            pat.search(cleaned_query) for pat in self._CONCEPTUAL_PATTERNS
        ) or (
            classification.query_type == QueryType.EXPLANATION
            and len(cleaned_query.split()) > 3
        )
        if is_conceptual:
            reasoning_signals.append("semantic_question_detected")
            reasoning_signals.append("conceptual_query_detected")
            return RetrievalDecision(
                strategy=RetrievalStrategy.HYDE,
                confidence=0.88,
                reasoning_signals=reasoning_signals,
                expected_evidence_targets=expected_targets,
                max_iterations=1,
                max_retrieval_calls=1,
            )

        # 4. Complex Multi-Intent / Ambiguous query -> HYBRID_ADAPTIVE
        if classification.query_type == QueryType.AMBIGUOUS:
            reasoning_signals.append("complex_multi_intent_detected")
            return RetrievalDecision(
                strategy=RetrievalStrategy.HYBRID_ADAPTIVE,
                confidence=classification.confidence,
                reasoning_signals=reasoning_signals,
                expected_evidence_targets=expected_targets,
                max_iterations=2,
                max_retrieval_calls=3,
            )

        # 5. Default: Direct factual query with strong lexical match -> STANDARD_HYBRID
        reasoning_signals.append("direct_factual_match")
        return RetrievalDecision(
            strategy=RetrievalStrategy.STANDARD_HYBRID,
            confidence=classification.confidence,
            reasoning_signals=reasoning_signals,
            expected_evidence_targets=expected_targets,
            max_iterations=1,
            max_retrieval_calls=1,
        )

    def _extract_evidence_targets(
        self, query: str, classification: QueryClassification
    ) -> list[str]:
        """Extracts expected evidence topics/targets from query for sufficiency validation."""
        # Check comparison or multi-hop split
        lower_q = query.lower()
        if " and " in lower_q or " vs " in lower_q or " compare " in lower_q:
            parts = re.split(
                r"\b(?:and|vs\.?|versus|compare|as well as)\b",
                query,
                flags=re.IGNORECASE,
            )
            cleaned_parts = [
                re.sub(
                    r"^(?:what\s+is|what\s+are|how\s+is|the|a|an)\s+",
                    "",
                    p.strip("?., "),
                    flags=re.IGNORECASE,
                ).strip()
                for p in parts
            ]
            valid_parts = [p for p in cleaned_parts if len(p) > 2]
            if len(valid_parts) >= 2:
                return valid_parts

        # Single target fallback: cleaned query essence
        essence = re.sub(
            r"^(?:what\s+is|what\s+are|how\s+does|explain|describe|tell\s+me\s+about)\s+(?:the\s+)?",
            "",
            query.strip("?., "),
            flags=re.IGNORECASE,
        ).strip()
        return [essence] if essence else [query.strip()]
