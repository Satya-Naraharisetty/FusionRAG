import pytest

from app.documents.services.query_classifier import QueryType
from app.documents.services.query_decomposer import (
    DeterministicQueryDecomposer,
    SafeQueryDecomposer,
)


@pytest.mark.asyncio
async def test_multi_hop_query_decomposition():
    decomposer = DeterministicQueryDecomposer()
    subtasks = await decomposer.decompose(
        "What was 2025 revenue growth and also the engineering SLA target?",
        query_type=QueryType.MULTI_HOP,
        max_subtasks=3,
    )
    assert len(subtasks) >= 2
    queries = [st.query.lower() for st in subtasks]
    assert any("revenue" in q for q in queries)
    assert any("sla" in q for q in queries)


@pytest.mark.asyncio
async def test_conservative_comparison_non_splitting():
    decomposer = DeterministicQueryDecomposer()
    # Simple comparison query must NOT be split
    subtasks = await decomposer.decompose(
        "Compare JWT and OAuth authentication",
        query_type=QueryType.COMPARISON,
        max_subtasks=3,
    )
    assert len(subtasks) == 1
    assert subtasks[0].query == "Compare JWT and OAuth authentication"


@pytest.mark.asyncio
async def test_multi_target_comparison_decomposition():
    decomposer = DeterministicQueryDecomposer()
    # Multi-target comparison query with compound conjuncts
    subtasks = await decomposer.decompose(
        "Compare standard tier vs enterprise tier availability as well as burst capacity across both",
        query_type=QueryType.COMPARISON,
        max_subtasks=3,
    )
    assert len(subtasks) >= 2


@pytest.mark.asyncio
async def test_factual_query_remains_single_subtask():
    decomposer = DeterministicQueryDecomposer()
    subtasks = await decomposer.decompose(
        "What is the standard availability SLO for enterprise tier tenants?",
        query_type=QueryType.FACTUAL,
        max_subtasks=3,
    )
    assert len(subtasks) == 1
    assert (
        subtasks[0].query
        == "What is the standard availability SLO for enterprise tier tenants?"
    )


@pytest.mark.asyncio
async def test_decomposition_respects_max_subtasks():
    decomposer = DeterministicQueryDecomposer()
    subtasks = await decomposer.decompose(
        "What is revenue? What is SLA? What is KMS key rotation? What is DR RTO?",
        query_type=QueryType.MULTI_HOP,
        max_subtasks=2,
    )
    assert len(subtasks) <= 2


@pytest.mark.asyncio
async def test_safe_query_decomposer_fallback_on_error():
    class FailingDecomposer:
        async def decompose(self, query, query_type=None, max_subtasks=3):
            raise RuntimeError("Decomposition crash")

    safe = SafeQueryDecomposer(decomposer=FailingDecomposer(), timeout_ms=500)
    subtasks = await safe.decompose("What is 2025 revenue and SLA target?")
    assert len(subtasks) == 1
    assert subtasks[0].query == "What is 2025 revenue and SLA target?"
