import logging
import math
from typing import Any

from app.chat.domain.interfaces import TokenEstimator

logger = logging.getLogger(__name__)


class CharacterTokenEstimator(TokenEstimator):
    """
    Simple character-based token estimator strategy (len(text) // 4).
    Matches the basic heuristic in ChunkingService.
    """

    def estimate(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        return max(1, len(text) // 4)


class TiktokenTokenizerAdapter(TokenEstimator):
    """
    Tokenizer adapter wrapping tiktoken BPE encodings (e.g. cl100k_base / o200k_base).
    Provides exact token counts with an optional safety margin buffer.
    """

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        safety_margin: float = 1.15,
    ) -> None:
        self._encoding_name = encoding_name
        self._safety_margin = max(1.0, safety_margin)
        self._encoding: Any = None
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception as exc:
            logger.warning(
                f"Failed to initialize tiktoken encoding '{encoding_name}': {exc}"
            )
            self._encoding = None

    def estimate(self, text: str) -> int:
        if not text or not text.strip():
            return 0

        if self._encoding is not None:
            try:
                raw_count = len(self._encoding.encode(text))
                return max(1, math.ceil(raw_count * self._safety_margin))
            except Exception as exc:
                logger.debug(f"Tiktoken encoding failed on text sample: {exc}")

        # Fallback if encoding is missing or encounters an encoding error
        return max(1, math.ceil(len(text) * 0.75 * self._safety_margin))


class AdaptiveTokenEstimator(TokenEstimator):
    """
    Multilingual adaptive token estimator.
    Uses tiktoken BPE tokenizer when available, with a calibrated conservative heuristic
    fallback for non-ASCII (CJK, Indic, Arabic, Cyrillic, Emoji), ASCII punctuation/symbols,
    and code/URLs to ensure estimated_tokens >= actual_tokens across all corpora.

    Heuristic formula:
      - ASCII alphanumeric & whitespace: ceil(N_alnum / 3.0)
      - ASCII punctuation & symbols: N_symbols * 1.0 (symbols in URLs/code produce individual tokens)
      - Non-ASCII / Unicode (CJK, Indic, Arabic, Emoji): ceil(N_unicode * 2.0)
      - Applied safety margin: 1.15x
    """

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        safety_margin: float = 1.15,
        use_tokenizer: bool = True,
    ) -> None:
        self._encoding_name = encoding_name
        self._safety_margin = max(1.0, safety_margin)
        self._use_tokenizer = use_tokenizer
        self._adapter: TiktokenTokenizerAdapter | None = None

        if use_tokenizer:
            try:
                self._adapter = TiktokenTokenizerAdapter(
                    encoding_name=encoding_name, safety_margin=safety_margin
                )
                if self._adapter._encoding is None:
                    self._adapter = None
            except Exception:
                self._adapter = None

    def _estimate_heuristic(self, text: str) -> int:
        ascii_alnum = 0
        ascii_symbols = 0
        unicode_chars = 0

        for char in text:
            code = ord(char)
            if code < 128:
                if char.isalnum() or char.isspace():
                    ascii_alnum += 1
                else:
                    ascii_symbols += 1
            else:
                unicode_chars += 1

        alnum_tokens = math.ceil(ascii_alnum / 3.0) if ascii_alnum > 0 else 0
        symbol_tokens = ascii_symbols
        unicode_tokens = math.ceil(unicode_chars * 2.0)

        heuristic = alnum_tokens + symbol_tokens + unicode_tokens
        return max(1, math.ceil(heuristic * self._safety_margin))

    def estimate(self, text: str) -> int:
        if not text or not text.strip():
            return 0

        if self._adapter is not None:
            try:
                return self._adapter.estimate(text)
            except Exception:
                pass

        return self._estimate_heuristic(text)
