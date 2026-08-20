import asyncio

import pytest

from app.documents.services.query_expansion import (
    LexicalQueryExpander,
    SafeQueryExpander,
)


@pytest.mark.asyncio
async def test_deterministic_lexical_expansion():
    expander = LexicalQueryExpander()
    queries = await expander.expand("JWT expiry", max_queries=3)

    assert len(queries) >= 2
    # Invariant: Original query is always preserved at index 0
    assert queries[0] == "JWT expiry"
    assert any(
        "json web token" in q.lower() or "expiration" in q.lower() for q in queries[1:]
    )


@pytest.mark.asyncio
async def test_expansion_always_preserves_original_query_at_index_zero():
    expander = LexicalQueryExpander()
    for raw in ["OAuth token", "SLA targets", "Qdrant vector latency"]:
        res = await expander.expand(raw, max_queries=3)
        assert res[0] == raw


@pytest.mark.asyncio
async def test_expansion_deduplicates_queries():
    expander = LexicalQueryExpander()
    queries = await expander.expand("JWT and jwt token", max_queries=5)
    lower_set = set()
    for q in queries:
        assert q.lower() not in lower_set
        lower_set.add(q.lower())


@pytest.mark.asyncio
async def test_expansion_respects_max_queries():
    expander = LexicalQueryExpander()
    queries = await expander.expand("JWT and OAuth and SLA and RAG", max_queries=2)
    assert len(queries) <= 2
    assert queries[0] == "JWT and OAuth and SLA and RAG"


@pytest.mark.asyncio
async def test_safe_query_expander_timeout_fallback():
    class SlowExpander:
        async def expand(self, query: str, context=None, max_queries=3):
            await asyncio.sleep(0.5)
            return ["slow 1", "slow 2"]

    safe = SafeQueryExpander(expander=SlowExpander(), timeout_ms=50, max_queries=3)
    res = await safe.expand("test query")
    assert res == ["test query"]


@pytest.mark.asyncio
async def test_safe_query_expander_error_fallback():
    class FailingExpander:
        async def expand(self, query: str, context=None, max_queries=3):
            raise RuntimeError("Expansion backend unavailable")

    safe = SafeQueryExpander(expander=FailingExpander(), timeout_ms=500, max_queries=3)
    res = await safe.expand("fallback test query")
    assert res == ["fallback test query"]
