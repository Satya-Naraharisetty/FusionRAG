import logging
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryClassifier,
    QueryType,
)

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    LIGHT = "LIGHT"
    HEAVY = "HEAVY"


class ModelRoutingDecision(BaseModel):
    selected_model: str
    tier: ModelTier
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    complexity_score: float = Field(ge=0.0, le=1.0, default=0.0)

    model_config = ConfigDict(frozen=True)


class ComplexityModelRouter:
    """
    Sub-millisecond, zero-API-cost model routing service.
    Dynamically routes synthesis requests between lightweight (fast, low-cost)
    and heavy (high-reasoning, multi-hop) models based on query complexity heuristics.
    """

    def __init__(
        self,
        enabled: bool = True,
        light_model: str = "gemini-3.5-flash-lite",
        heavy_model: str = "gemini-2.5-flash",
        query_classifier: QueryClassifier | None = None,
        complexity_threshold: float = 0.6,
    ) -> None:
        self.enabled = enabled
        self.light_model = light_model
        self.heavy_model = heavy_model
        self._classifier = query_classifier or DeterministicQueryClassifier()
        self.complexity_threshold = complexity_threshold

    def resolve_model(
        self,
        query: str,
        classification: QueryClassification | None = None,
        fallback_model: str | None = None,
        context_tokens: int = 0,
    ) -> ModelRoutingDecision:
        """
        Resolves the optimal LLM model for the given query without making any external API calls.
        """
        default_model = fallback_model or self.light_model

        if not self.enabled:
            return ModelRoutingDecision(
                selected_model=default_model,
                tier=ModelTier.LIGHT
                if default_model == self.light_model
                else ModelTier.HEAVY,
                reason="routing_disabled",
                confidence=1.0,
                complexity_score=0.0,
            )

        cleaned_query = query.strip()
        if not cleaned_query:
            return ModelRoutingDecision(
                selected_model=self.light_model,
                tier=ModelTier.LIGHT,
                reason="empty_query",
                confidence=1.0,
                complexity_score=0.0,
            )

        if classification is None:
            classification = self._classifier.classify(cleaned_query)

        # Baseline complexity mapped by query type
        type_scores: dict[QueryType, float] = {
            QueryType.CONVERSATIONAL: 0.10,
            QueryType.FACTUAL: 0.30,
            QueryType.AMBIGUOUS: 0.30,
            QueryType.EXPLANATION: 0.55,
            QueryType.NUMERICAL: 0.70,
            QueryType.TABLE: 0.85,
            QueryType.GRAPH: 0.85,
            QueryType.COMPARISON: 0.85,
            QueryType.MULTI_DOCUMENT: 0.90,
            QueryType.MULTI_HOP: 0.95,
        }
        score = type_scores.get(classification.query_type, 0.40)
        reasons: list[str] = [f"type_{classification.query_type.value.lower()}"]

        # Modifier boosts
        if classification.requires_decomposition:
            score = max(score, 0.85)
            reasons.append("requires_decomposition")

        if classification.has_multiple_evidence_targets:
            score = max(score, 0.80)
            reasons.append("multiple_targets")

        if re.search(
            r"\b(and\s+(what|who|where|how|why|when|which))\b",
            cleaned_query,
            re.IGNORECASE,
        ):
            score = max(score, 0.75)
            reasons.append("compound_question")

        if cleaned_query.count("?") > 1:
            score = max(score, 0.80)
            reasons.append("multi_question")

        if len(cleaned_query) > 350:
            score = min(1.0, score + 0.15)
            reasons.append("long_query")

        if context_tokens > 4000:
            score = min(1.0, score + 0.15)
            reasons.append("large_context")

        is_heavy = score >= self.complexity_threshold
        chosen_model = self.heavy_model if is_heavy else self.light_model
        tier = ModelTier.HEAVY if is_heavy else ModelTier.LIGHT
        reason_str = "+".join(reasons)

        logger.info(
            "ModelRouter: routed '%s' (score=%.2f, threshold=%.2f) -> %s (%s, reason=%s)",
            cleaned_query[:40],
            score,
            self.complexity_threshold,
            chosen_model,
            tier.value,
            reason_str,
        )

        return ModelRoutingDecision(
            selected_model=chosen_model,
            tier=tier,
            reason=reason_str,
            confidence=classification.confidence,
            complexity_score=round(score, 3),
        )
