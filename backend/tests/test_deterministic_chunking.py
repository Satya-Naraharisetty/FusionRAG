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
    assert len(chunk_ids) == len(set(chunk_ids)), "All chunk IDs in a document must be unique"
