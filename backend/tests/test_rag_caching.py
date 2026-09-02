import uuid

import pytest

from app.chat.services.rag_cache_service import RAGCacheService
from app.core.cache.memory_cache import InMemoryCache
from app.core.security.crypto import EnvelopeEncryptionService


@pytest.mark.asyncio
async def test_rag_cache_key_determinism_and_scoping():
    cache = InMemoryCache()
    service = RAGCacheService(cache=cache, enabled=True)

    user1 = uuid.uuid4()
    user2 = uuid.uuid4()
    conv_id = uuid.uuid4()
    parent_msg = uuid.uuid4()
    doc1 = uuid.uuid4()

    # 1. Normalization (whitespace, case)
    key1 = service.compute_cache_key(
        user_id=user1,
        conversation_id=conv_id,
        parent_message_id=parent_msg,
        query="  What is the Return Policy?  ",
        doc_versions={doc1: 1},
    )
    key2 = service.compute_cache_key(
        user_id=user1,
        conversation_id=conv_id,
        parent_message_id=parent_msg,
        query="what is the return policy?",
        doc_versions={doc1: 1},
    )
    assert key1 == key2

    # 2. Multi-tenant isolation (user1 vs user2)
    key_user2 = service.compute_cache_key(
        user_id=user2,
        conversation_id=conv_id,
        parent_message_id=parent_msg,
        query="what is the return policy?",
        doc_versions={doc1: 1},
    )
    assert key1 != key_user2

    # 3. Active version invalidation (doc1 version 1 vs 2)
    key_v2 = service.compute_cache_key(
        user_id=user1,
        conversation_id=conv_id,
        parent_message_id=parent_msg,
        query="what is the return policy?",
        doc_versions={doc1: 2},
    )
    assert key1 != key_v2

    # 4. Branching isolation (parent_message_id)
    key_branch2 = service.compute_cache_key(
        user_id=user1,
        conversation_id=conv_id,
        parent_message_id=uuid.uuid4(),
        query="what is the return policy?",
        doc_versions={doc1: 1},
    )
    assert key1 != key_branch2


@pytest.mark.asyncio
async def test_rag_cache_service_encryption_and_decryption():
    cache = InMemoryCache()
    crypto = EnvelopeEncryptionService(master_key="test-master-key-32-chars-length!")
    service = RAGCacheService(cache=cache, crypto=crypto, enabled=True)

    user_id = uuid.uuid4()
    user_dek = crypto.generate_user_dek()
    key = "rag:ans:test_encrypted_key"
    payload = {
        "answer": "The annual revenue was $5.4M in 2024.",
        "citations": [{"document_id": str(uuid.uuid4()), "chunk_index": 0}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
    }

    # Set encrypted response
    saved = await service.set_cached_response(
        key=key,
        payload=payload,
        user_id=user_id,
        user_dek=user_dek,
        ttl=3600,
    )
    assert saved is True

    # Check raw cache representation (is encrypted)
    raw_item = await cache.get(key)
    assert isinstance(raw_item, dict)
    assert raw_item.get("encrypted") is True
    assert "ciphertext" in raw_item

    # Get with valid DEK
    decrypted = await service.get_cached_response(
        key=key,
        user_dek=user_dek,
        user_id=user_id,
    )
    assert decrypted is not None
    assert decrypted["answer"] == payload["answer"]
    assert decrypted["usage"]["total_tokens"] == 165

    # Get with invalid/wrong DEK returns None
    wrong_dek = crypto.generate_user_dek()
    invalid_result = await service.get_cached_response(
        key=key,
        user_dek=wrong_dek,
        user_id=user_id,
    )
    assert invalid_result is None


@pytest.mark.asyncio
async def test_rag_cache_service_should_cache_gating():
    cache = InMemoryCache()
    service = RAGCacheService(cache=cache, enabled=True, min_confidence=0.70)

    # 1. Valid answer
    assert (
        service.should_cache_response(
            answer="According to section 4, the reimbursement is $50.",
            status="completed",
        )
        is True
    )

    # 2. Refusal answer
    assert (
        service.should_cache_response(
            answer="I do not have enough evidence to answer your question.",
            status="completed",
        )
        is False
    )

    # 3. Non-completed status
    assert (
        service.should_cache_response(
            answer="Valid text",
            status="failed",
        )
        is False
    )

    # 4. WebSearchAgent in plan
    assert (
        service.should_cache_response(
            answer="Current AAPL stock is $225.",
            agent_diagnostics={"executed_agents": ["WebSearchAgent", "SynthesisAgent"]},
            status="completed",
        )
        is False
    )

    # 5. Low evidence score
    assert (
        service.should_cache_response(
            answer="Maybe the answer is X.",
            agent_diagnostics={"evidence_score": 0.45},
            status="completed",
        )
        is False
    )


@pytest.mark.asyncio
async def test_rag_cache_service_stream_replay():
    cache = InMemoryCache()
    service = RAGCacheService(cache=cache, enabled=True, stream_delay_ms=0.0)

    cached_payload = {
        "answer": "This is a cached streaming test response.",
        "citations": [{"document_id": str(uuid.uuid4()), "chunk_index": 1}],
        "diagnostics": {"dense_count": 1},
    }
    assistant_msg_id = uuid.uuid4()
    conv_id = uuid.uuid4()

    events = []
    async for event in service.replay_stream_events(
        cached_payload=cached_payload,
        assistant_message_id=assistant_msg_id,
        conversation_id=conv_id,
    ):
        events.append(event)

    event_names = [e["event"] for e in events]
    assert "metadata" in event_names
    assert "text" in event_names
    assert "synthesis_done" in event_names
    assert "done" in event_names

    # Check cache_hit flag in metadata and done events
    metadata_ev = next(e for e in events if e["event"] == "metadata")
    assert metadata_ev["data"]["diagnostics"]["cache_hit"] is True

    done_ev = next(e for e in events if e["event"] == "done")
    assert done_ev["data"]["diagnostics"]["cache_hit"] is True
    assert done_ev["data"]["answer"] == cached_payload["answer"]


@pytest.mark.asyncio
async def test_rag_cache_service_global_cross_user_caching():
    cache = InMemoryCache()
    service = RAGCacheService(cache=cache, enabled=True)

    user1 = uuid.uuid4()
    user2 = uuid.uuid4()
    query = "How do I calculate factorial in Python?"

    user1_key = service.compute_cache_key(
        user_id=user1,
        conversation_id=uuid.uuid4(),
        parent_message_id=None,
        query=query,
        doc_versions=None,
    )
    user2_key = service.compute_cache_key(
        user_id=user2,
        conversation_id=uuid.uuid4(),
        parent_message_id=None,
        query=query,
        doc_versions=None,
    )
    global_key = service.compute_global_cache_key(query=query)

    assert user1_key != user2_key
    assert (
        global_key
        == "rag:ans:global:root:no_docs:"
        + service.compute_global_cache_key(query).split(":")[-1]
    )

    # User 1 performs standalone general query (no citations, no docs)
    payload = {
        "answer": "Use math.factorial(n) in Python standard library.",
        "citations": [],
        "usage": {"total_tokens": 50},
    }
    await service.set_cached_response(
        key=user1_key,
        payload=payload,
        user_id=user1,
        global_key=global_key,
    )

    # User 2 performs same general query with empty User 2 cache
    user2_hit = await service.get_cached_response(
        key=user2_key,
        user_id=user2,
        fallback_global_key=global_key,
    )
    assert user2_hit is not None
    assert user2_hit["answer"] == payload["answer"]

    # Verify that private document queries are NEVER written to global cache
    doc_query = "What is the secret acquisition price?"
    doc_user1_key = service.compute_cache_key(
        user_id=user1,
        conversation_id=uuid.uuid4(),
        parent_message_id=None,
        query=doc_query,
        doc_versions={uuid.uuid4(): 1},
    )
    doc_global_key = service.compute_global_cache_key(query=doc_query)
    doc_payload = {
        "answer": "Acquisition price is $100M.",
        "citations": [{"document_id": str(uuid.uuid4()), "chunk_index": 0}],
    }
    # Attempting to pass global_key with citations
    await service.set_cached_response(
        key=doc_user1_key,
        payload=doc_payload,
        user_id=user1,
        global_key=doc_global_key,
    )

    # User 2 must NOT receive User 1's private document answer
    doc_user2_key = service.compute_cache_key(
        user_id=user2,
        conversation_id=uuid.uuid4(),
        parent_message_id=None,
        query=doc_query,
        doc_versions=None,
    )
    user2_doc_attempt = await service.get_cached_response(
        key=doc_user2_key,
        user_id=user2,
        fallback_global_key=doc_global_key,
    )
    assert user2_doc_attempt is None
