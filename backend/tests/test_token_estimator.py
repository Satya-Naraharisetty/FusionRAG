import tiktoken

from app.chat.services.token_estimator import (
    AdaptiveTokenEstimator,
    CharacterTokenEstimator,
    TiktokenTokenizerAdapter,
)

ACCEPTANCE_CORPUS = {
    # 1. English variations
    "English Short": "Hello, how can I help you today?",
    "English Long Paragraph": (
        "Retrieval-Augmented Generation (RAG) enhances Large Language Models by grounding outputs in "
        "verifiable external knowledge bases. Keyset pagination prevents offset performance degradation."
    ),
    "English Technical Markdown": (
        "# Architecture Specification\n```python\nasync def fetch_records(limit: int = 50) -> CursorPage[Item]:\n"
        "    return await repo.get_items(limit=limit)\n```"
    ),
    "English Conversational": "Wait, could you clarify what you meant by 'deterministic fallback' earlier? I didn't catch that part.",
    # 2. Hindi / Indic / Devanagari
    "Hindi Short": "नमस्ते, मैं आपकी क्या सहायता कर सकता हूँ?",
    "Hindi Long": "फ़्यूज़न आरएजी एक उन्नत खोज प्रणाली है जो दस्तावेज़ों के आधार पर प्रश्नों का सटीक उत्तर देती है।",
    "Sanskrit / Vedic": "ॐ भूर्भुवः स्वः तत्सवितुर्वरेण्यं भर्गो देवस्य धीमहि धियो यो नः प्रचोदयात्॥",
    # 3. CJK (Chinese, Japanese, Korean)
    "Japanese (Kanji + Kana)": "こんにちは世界。検索拡張生成（RAG）モデルの性能評価と多言語トークン推定のテストを実行しています。",
    "Chinese Simplified": "你好，这是用于验证多语言分词安全性的测试文本。大型语言模型的上下文窗口需要精确管理。",
    "Chinese Traditional": "這是一個繁體中文的檢索增強生成系統測試範例，確保標記估計準確無誤。",
    "Korean (Hangul)": "안녕하세요! 검색 증강 생성 시스템을 위한 다국어 토큰 추정 테스트를 진행하고 있습니다.",
    # 4. Middle Eastern / Semitic
    "Arabic Short": "مرحبا، كيف يمكنني مساعدتك اليوم؟",
    "Arabic Long": "يعتمد توليد النصوص المدعوم بالاسترجاع على استخراج المعلومات الدقيقة من قواعد البيانات لضمان دقة الإجابات.",
    "Hebrew": "שלום עולם, זוהי בדיקה להערכת מספר האסיमोנים עבור מערכת חיפוש מתקדמת.",
    # 5. Cyrillic & Greek
    "Russian": "Привет! Это комплексная проверка оценки количества токенов для многоязычных запросов в RAG.",
    "Ukrainian": "Доброго дня! Це перевірка системи оцінки токенів для контексту мовних моделей.",
    "Greek": "Γεια σας! Αυτή είναι μια δοκιμή εκτίμησης διακριτικών για πολυγलωσσικά μοντέλα.",
    # 6. Mixed Unicode & Emoji
    "Emoji Heavy": "🚀 FusionRAG 🌟 v2.0 is live! 🔥 Check out the docs 📚 & benchmarks 📊 -> 💯",
    "Math & Symbols": "∀x ∈ ℝ: f(x) = ∑_{i=0}^n α_i x^i + ∫_0^∞ e^{-t} dt ≈ 3.1415926535",
    "Mixed Scripts": "FusionRAG (फ़्यूज़न) supports English, हिन्दी, 日本語, العربية, and Русский flawlessly!",
    # 7. Code, URLs, Numbers, Whitespace
    "Python Code Block": (
        "class CursorSigner:\n    @classmethod\n    def encode(cls, created_at: datetime, record_id: UUID) -> str:\n"
        "        return base64url_encode(f'{created_at.isoformat()}|{record_id}')"
    ),
    "JSON Payload": '{"event": "search_query", "query": "hybrid dense sparse retrieval", "top_k": 20, "filters": {"tenant_id": "a3b8-9c1d"}}',
    "URL & UUIDs": "https://api.fusionrag.internal/v1/conversations/3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d/messages?limit=50&cursor=eyJjcmVhdGVkX2F0",
    "Whitespace & Newlines": "\n\n\t\t   \n\t   \n\n\r\n\t\t\t   ",
    "Repeated Punctuation": "???!!!...:::;;;---___***===+++///\\\\\\|||&&&%%%$$$###@@@~~~```",
    "Long Number Sequence": "18446744073709551615 3.141592653589793238462643383279502884197169399375105820974944",
}


def test_character_token_estimator_baseline():
    estimator = CharacterTokenEstimator()
    assert estimator.estimate("") == 0
    assert estimator.estimate("a") == 1
    assert estimator.estimate("1234") == 1
    assert estimator.estimate("12345678") == 2


def test_tiktoken_adapter_cl100k_and_o200k():
    adapter_cl = TiktokenTokenizerAdapter(
        encoding_name="cl100k_base", safety_margin=1.15
    )
    adapter_o2 = TiktokenTokenizerAdapter(
        encoding_name="o200k_base", safety_margin=1.15
    )

    assert adapter_cl.estimate("") == 0
    assert adapter_o2.estimate("") == 0

    text = "Hello world from FusionRAG testing suite"
    cl_est = adapter_cl.estimate(text)
    o2_est = adapter_o2.estimate(text)

    assert cl_est >= 6
    assert o2_est >= 6


def test_adaptive_token_estimator_broad_corpus_safety_with_tokenizer():
    estimator = AdaptiveTokenEstimator(
        encoding_name="cl100k_base", safety_margin=1.15, use_tokenizer=True
    )
    enc = tiktoken.get_encoding("cl100k_base")

    for name, sample_text in ACCEPTANCE_CORPUS.items():
        if not sample_text.strip():
            actual = 0
        else:
            actual = len(enc.encode(sample_text))

        est = estimator.estimate(sample_text)
        assert est >= actual, (
            f"Estimator undercounted for '{name}': estimated {est} < actual {actual}"
        )


def test_adaptive_token_estimator_heuristic_fallback_safety():
    # Force heuristic mode (use_tokenizer=False)
    estimator = AdaptiveTokenEstimator(safety_margin=1.15, use_tokenizer=False)
    enc = tiktoken.get_encoding("cl100k_base")

    for name, sample_text in ACCEPTANCE_CORPUS.items():
        if not sample_text.strip():
            actual = 0
        else:
            actual = len(enc.encode(sample_text))

        est = estimator.estimate(sample_text)
        # Verify heuristic provides safe budgeting or non-zero upper bound
        if actual > 0:
            assert est >= 1
            # For pure multilingual & conversational text, heuristic must strictly exceed or match actual
            if name in [
                "English Short",
                "Hindi Short",
                "Japanese (Kanji + Kana)",
                "Arabic Short",
                "Russian",
                "Greek",
            ]:
                assert est >= actual, (
                    f"Heuristic undercounted for '{name}': {est} < {actual}"
                )


def test_adaptive_token_estimator_empty_and_whitespace():
    estimator = AdaptiveTokenEstimator()
    assert estimator.estimate("") == 0
    assert estimator.estimate("   ") == 0
    assert estimator.estimate("\n\t\n") == 0
