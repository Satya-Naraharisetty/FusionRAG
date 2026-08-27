import uuid

from app.documents.services.chunking import ChunkingService


def test_deterministic_chunk_ids_identical_for_same_version():
    chunker = ChunkingService(chunk_size=100, chunk_overlap=10)
    doc_id = uuid.uuid4()
    checksum = "a1b2c3d4e5f678901234567890abcdef"
    text = "This is a test paragraph for chunking. " * 10

    result1 = chunker.chunk_document(text, doc_id, checksum=checksum)
    result2 = chunker.chunk_document(text, doc_id, checksum=checksum)

    assert len(result1.chunks) > 0
    assert len(result1.chunks) == len(result2.chunks)

    # Every chunk must have the EXACT same deterministic UUID
    for c1, c2 in zip(result1.chunks, result2.chunks, strict=True):
        assert c1.id == c2.id
        assert c1.chunk_index == c2.chunk_index
        assert c1.text == c2.text


def test_deterministic_chunk_ids_diverge_for_different_checksums():
    chunker = ChunkingService(chunk_size=100, chunk_overlap=10)
    doc_id = uuid.uuid4()
    checksum_v1 = "checksum_v1_11111111111111111111"
    checksum_v2 = "checksum_v2_22222222222222222222"
    text = "This is a test paragraph for chunking. " * 10

    result_v1 = chunker.chunk_document(text, doc_id, checksum=checksum_v1)
    result_v2 = chunker.chunk_document(text, doc_id, checksum=checksum_v2)

    assert len(result_v1.chunks) > 0
    assert len(result_v1.chunks) == len(result_v2.chunks)

    # Different checksums on same doc_id must yield DIFFERENT chunk IDs (no cross-version collisions)
    for c1, c2 in zip(result_v1.chunks, result_v2.chunks, strict=True):
        assert c1.id != c2.id
        assert c1.chunk_index == c2.chunk_index


def test_chunk_ids_distinct_across_indices():
    chunker = ChunkingService(chunk_size=50, chunk_overlap=5, min_chunk_size=10)
    doc_id = uuid.uuid4()
    checksum = "some_unique_checksum"
    text = "Sentence one is here. Sentence two is here. Sentence three is here. Sentence four is here."

    result = chunker.chunk_document(text, doc_id, checksum=checksum)
    assert len(result.chunks) > 1

    chunk_ids = [c.id for c in result.chunks]
    assert len(chunk_ids) == len(set(chunk_ids)), (
        "All chunk IDs in a document must be unique"
    )


def test_parent_child_chunking_deterministic_and_linked():
    chunker = ChunkingService(
        parent_chunk_size=200,
        parent_chunk_overlap=20,
        child_chunk_size=60,
        child_chunk_overlap=10,
        min_chunk_size=10,
        enable_parent_child=True,
    )
    doc_id = uuid.uuid4()
    checksum = "chk_parent_child_12345"
    text = (
        "Section 1 introduces the core architecture of the system. It describes the data layers and services. "
        "Section 2 details the background task execution engine and worker model. "
        "Section 3 covers the telemetry and observability stack with Prometheus and Jaeger."
    )

    result1 = chunker.chunk_document(text, doc_id, checksum=checksum)
    result2 = chunker.chunk_document(text, doc_id, checksum=checksum)

    assert len(result1.chunks) > 1
    assert len(result1.chunks) == len(result2.chunks)

    # Verify deterministic IDs across runs
    for c1, c2 in zip(result1.chunks, result2.chunks, strict=True):
        assert c1.id == c2.id
        assert c1.metadata["parent_chunk_id"] == c2.metadata["parent_chunk_id"]
        assert c1.metadata["parent_text"] == c2.metadata["parent_text"]
        assert c1.metadata["chunk_type"] == "child"
        assert len(c1.metadata["parent_text"]) >= len(c1.text)


def test_sentence_window_chunking_boundaries_and_windows():
    chunker = ChunkingService(
        sentence_window_size=2,
        enable_sentence_window=True,
    )
    doc_id = uuid.uuid4()
    checksum = "chk_sent_window_999"
    text = "First sentence is alpha. Second sentence is beta. Third sentence is gamma. Fourth sentence is delta. Fifth sentence is epsilon."

    result = chunker.chunk_document(text, doc_id, checksum=checksum)
    assert len(result.chunks) == 5

    # Check third sentence (index 2: "Third sentence is gamma.")
    c3 = result.chunks[2]
    assert c3.text == "Third sentence is gamma."
    assert c3.metadata["sentence_index"] == 2
    assert c3.metadata["window_size"] == 2
    # Surrounding window should contain all 5 sentences
    assert "First sentence is alpha." in c3.metadata["window_text"]
    assert "Fifth sentence is epsilon." in c3.metadata["window_text"]

    # Check first sentence (index 0) - beginning boundary
    c1 = result.chunks[0]
    assert c1.text == "First sentence is alpha."
    assert c1.metadata["sentence_index"] == 0
    # Window should contain sentences 0, 1, 2
    assert "First sentence is alpha." in c1.metadata["window_text"]
    assert "Third sentence is gamma." in c1.metadata["window_text"]
    assert "Fourth sentence is delta." not in c1.metadata["window_text"]


def test_contextual_retrieval_chunking_enrichment():
    chunker = ChunkingService(
        chunk_size=100,
        chunk_overlap=10,
        enable_contextual=True,
    )
    doc_id = uuid.uuid4()
    doc_name = "architecture_spec_v2.pdf"
    text = "The system uses Redis Streams for durable queueing. Handlers process documents asynchronously."

    result = chunker.chunk_document(text, doc_id, document_name=doc_name)
    assert len(result.chunks) > 0

    chunk = result.chunks[0]
    # Raw text must remain pristine
    assert "architecture_spec_v2.pdf" not in chunk.text
    # Contextual text in metadata must include document header
    assert f"[Document: {doc_name}]" in chunk.metadata["contextual_text"]
    assert chunk.text in chunk.metadata["contextual_text"]
