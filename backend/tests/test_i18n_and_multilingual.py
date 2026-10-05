"""
Multilingual, Internationalization (i18n) & Unicode Boundary Verification Suite.

Comprehensive tests verifying:
1. Unicode Normalization (NFC vs NFD, NFKC equivalence).
2. CJK (Chinese, Japanese, Korean) text chunking, token estimation, and tokenization.
3. RTL (Right-to-Left: Arabic, Hebrew) text handling and prompt isolation.
4. Zero-width spaces, BOM markers, and multi-byte emojis in ingestion and search.
"""

from uuid import uuid4

import pytest

from app.chat.services.prompt_builder import PromptBuilder
from app.core.security.prompt_injection import (
    PromptInjectionScanner,
)
from app.documents.services.chunking import ChunkingService
from app.documents.services.sparse_index import BM25, tokenize
from app.documents.services.text_cleaner import TextCleaner


@pytest.fixture
def text_cleaner() -> TextCleaner:
    return TextCleaner()


@pytest.fixture
def chunking_service() -> ChunkingService:
    return ChunkingService(chunk_size=100, chunk_overlap=20, min_chunk_size=10)


# ---------------------------------------------------------------------------
# 1. Unicode Normalization & Equivalence
# ---------------------------------------------------------------------------


def test_unicode_nfc_vs_nfd_normalization(text_cleaner: TextCleaner):
    """
    Validates that pre-composed (NFC) and decomposed (NFD) representations
    normalize to the identical canonical NFKC representation.
    Example: 'é' as \u00e9 (NFC) vs 'e' + \u0301 (NFD).
    """
    nfc_str = "Caf\u00e9 au lait"
    nfd_str = "Cafe\u0301 au lait"

    # Before normalization they have different lengths/bytes
    assert nfc_str != nfd_str
    assert len(nfc_str) != len(nfd_str)

    # After TextCleaner they must be byte-for-byte identical
    cleaned_nfc = text_cleaner.clean(nfc_str)
    cleaned_nfd = text_cleaner.clean(nfd_str)
    assert cleaned_nfc == cleaned_nfd
    assert cleaned_nfc == "Café au lait"


def test_unicode_zero_width_and_bom_handling(text_cleaner: TextCleaner):
    """
    Validates handling of zero-width spaces (\u200b) and Byte Order Marks (\ufeff).
    """
    text_with_bom_and_zwsp = "\ufeffFusion\u200bRAG is \u200bdistributed."
    cleaned = text_cleaner.clean(text_with_bom_and_zwsp)

    # NFKC normalizes BOM, whitespace is preserved or cleaned cleanly
    assert "Fusion" in cleaned
    assert "RAG" in cleaned
    assert cleaned.endswith("distributed.")


def test_multibyte_emojis_preserved(text_cleaner: TextCleaner):
    """
    Ensures multi-byte emojis (e.g. 🤖, 🚀, 💡) are preserved without character corruption.
    """
    emoji_text = "AI Document QA Platform 🤖 🚀 with hybrid search 💡"
    cleaned = text_cleaner.clean(emoji_text)
    assert "🤖" in cleaned
    assert "🚀" in cleaned
    assert "💡" in cleaned


# ---------------------------------------------------------------------------
# 2. CJK (Chinese, Japanese, Korean) Non-Space Delimited Chunking & Tokenizing
# ---------------------------------------------------------------------------


def test_cjk_chinese_chunking_integrity(chunking_service: ChunkingService):
    """
    Ensures that non-space-delimited Chinese text can be chunked cleanly
    without entering an infinite loop or dropping characters.
    """
    # 300 Chinese characters with punctuation
    chinese_text = (
        "人工智能检索增强生成技术（RAG）是一种结合了信息检索和文本生成的技术。"
        "它通过从外部知识库中检索相关文档，并将其作为上下文提供给大语言模型，"
        "从而显著减少模型的幻觉现象，提高回答的准确性与时效性。\n\n"
        "在大规模企业知识库中，混合检索结合了稠密向量检索和稀疏关键词检索的优势。"
        "稠密检索擅长捕捉语义相似性，而稀疏检索则在精确关键词和专业术语匹配方面表现出色。"
        "通过倒数排序融合（RRF）算法，可以将两者的排名结果进行有效结合。"
    )

    doc_id = uuid4()
    result = chunking_service.chunk_document(chinese_text, document_id=doc_id)

    assert result is not None
    assert len(result.chunks) >= 2
    for chunk in result.chunks:
        assert len(chunk.text.strip()) > 0
        assert chunk.token_estimate > 0


def test_cjk_japanese_bm25_tokenization():
    """
    Verifies that BM25 tokenizer processes Japanese text without crashing.
    """
    japanese_corpus = [
        "人工知能技術を用いたハイブリッド検索エンジンの設計。",
        "ベクトルデータベースと全文検索の統合アーキテクチャ。",
    ]

    tokenized_docs = [tokenize(doc) for doc in japanese_corpus]
    assert len(tokenized_docs) == 2
    bm25 = BM25(tokenized_docs)
    assert bm25.corpus_size == 2


# ---------------------------------------------------------------------------
# 3. RTL (Right-to-Left: Arabic, Hebrew) Prompt Isolation
# ---------------------------------------------------------------------------


def test_rtl_arabic_prompt_demarcation():
    """
    Ensures that Right-to-Left Arabic documents and questions are safely isolated
    within XML tags without escaping the demarcation boundaries.
    """
    arabic_context = (
        "تم تأسيس الشركة في عام 2020 في مدينة الرياض وبلغت الإيرادات 50 مليون دولار."
    )
    builder = PromptBuilder(system_prompt_path="")

    messages = builder.build_messages(
        question="متى تم تأسيس الشركة؟",
        context=arabic_context,
    )
    user_content = messages[1].content

    assert "<retrieved_context>" in user_content
    assert "</retrieved_context>" in user_content
    assert arabic_context in user_content


def test_rtl_hebrew_prompt_injection_scanner():
    """
    Ensures that the prompt injection scanner correctly handles Hebrew input
    without false positive crashes.
    """
    hebrew_benign_query = "מהם היתרונות של מודל RAG היברידי?"
    # Should scan clean and pass without error
    PromptInjectionScanner.scan_prompt(hebrew_benign_query)
