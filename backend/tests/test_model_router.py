import pytest

from app.chat.services.model_router import (
    ComplexityModelRouter,
    ModelTier,
)
from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryType,
)


@pytest.fixture
def classifier():
    return DeterministicQueryClassifier()


@pytest.fixture
def router(classifier):
    return ComplexityModelRouter(
        enabled=True,
        light_model="gemini-3.5-flash-lite",
        heavy_model="gemini-2.5-flash",
        query_classifier=classifier,
        complexity_threshold=0.6,
    )


def test_router_disabled_returns_fallback_model():
    router = ComplexityModelRouter(
        enabled=False,
        light_model="gemini-3.5-flash-lite",
        heavy_model="gemini-2.5-flash",
    )
    decision = router.resolve_model(
        query="Compare Q1 and Q2 revenues across all files",
        fallback_model="custom-model",
    )
    assert decision.selected_model == "custom-model"
    assert decision.reason == "routing_disabled"


def test_empty_query_routes_to_light_model(router):
    decision = router.resolve_model("   ")
    assert decision.selected_model == "gemini-3.5-flash-lite"
    assert decision.tier == ModelTier.LIGHT
    assert decision.reason == "empty_query"


def test_simple_conversational_routes_to_light_model(router):
    queries = [
        "hello",
        "hi, how are you?",
        "good morning",
        "thanks for the help",
    ]
    for q in queries:
        decision = router.resolve_model(q)
        assert decision.tier == ModelTier.LIGHT, (
            f"Expected LIGHT for '{q}', got {decision.tier}"
        )
        assert decision.selected_model == "gemini-3.5-flash-lite"


def test_simple_factual_routes_to_light_model(router):
    decision = router.resolve_model("What is the definition of AES?")
    assert decision.tier == ModelTier.LIGHT
    assert decision.selected_model == "gemini-3.5-flash-lite"


def test_comparison_routes_to_heavy_model(router):
    decision = router.resolve_model(
        "Compare the pros and cons of AES-GCM versus ChaCha20"
    )
    assert decision.tier == ModelTier.HEAVY
    assert decision.selected_model == "gemini-2.5-flash"
    assert (
        "comparison" in decision.reason or "requires_decomposition" in decision.reason
    )


def test_multi_hop_routes_to_heavy_model(router):
    decision = router.resolve_model(
        "Who was the CEO of the company that acquired Acme and what was the purchase price?"
    )
    assert decision.tier == ModelTier.HEAVY
    assert decision.selected_model == "gemini-2.5-flash"
    assert decision.complexity_score >= 0.6


def test_multi_document_routes_to_heavy_model(router):
    decision = router.resolve_model(
        "Compare the numbers across both documents and cross-reference them"
    )
    assert decision.tier == ModelTier.HEAVY
    assert decision.selected_model == "gemini-2.5-flash"


def test_table_and_numerical_routes_to_heavy_model(router):
    decision = router.resolve_model(
        "From the financial table, calculate the total revenue for FY 2025"
    )
    assert decision.tier == ModelTier.HEAVY
    assert decision.selected_model == "gemini-2.5-flash"


def test_context_token_boost(router):
    # Factual query normally routes to LIGHT, but with huge context tokens it should escalate to HEAVY
    decision_normal = router.resolve_model(
        "What is the policy number?", context_tokens=500
    )
    assert decision_normal.tier == ModelTier.LIGHT

    decision_large_ctx = router.resolve_model(
        "What is the policy number?", context_tokens=5000
    )
    assert "large_context" in decision_large_ctx.reason
    assert decision_large_ctx.complexity_score > decision_normal.complexity_score


def test_preclassified_query_override(router):
    custom_classification = QueryClassification(
        query_type=QueryType.MULTI_HOP,
        confidence=0.99,
        requires_decomposition=True,
    )
    decision = router.resolve_model(
        query="Short query",
        classification=custom_classification,
    )
    assert decision.tier == ModelTier.HEAVY
    assert decision.selected_model == "gemini-2.5-flash"


def test_chat_orchestrator_resolve_effective_model_helper():
    from unittest.mock import MagicMock

    from app.chat.services.chat_orchestrator import ChatOrchestrator

    # Mock minimal dependencies
    orch = ChatOrchestrator(
        retrieval_service=MagicMock(),
        prompt_builder=MagicMock(),
        llm_generation_service=MagicMock(),
        token_estimator=MagicMock(),
        conversation_manager=MagicMock(),
        context_builder=MagicMock(),
        agent_executor=MagicMock(),
        model="default-model",
        model_router=None,
    )
    # Without router: falls back to orch.model
    model, reason = orch._resolve_effective_model("Compare apples to oranges")
    assert model == "default-model"
    assert reason is None

    # With router attached:
    router = ComplexityModelRouter(
        enabled=True,
        light_model="gemini-3.5-flash-lite",
        heavy_model="gemini-2.5-flash",
    )
    orch.model_router = router

    model_light, _ = orch._resolve_effective_model("hello")
    assert model_light == "gemini-3.5-flash-lite"

    model_heavy, _ = orch._resolve_effective_model("Compare the two files in detail")
    assert model_heavy == "gemini-2.5-flash"
