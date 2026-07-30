import re
import unicodedata


class TextCleaner:
    def clean(self, text: str) -> str:
        """
        Normalizes and cleans the extracted text.
        - Unicode normalization (NFKC)
        - Horizontal whitespace normalization (repeated spaces/tabs to a single space)
        - Line ending normalization to \n
        - Excess blank lines removal (maximum of 2 consecutive newlines, preserving paragraph boundaries)
        """
        if not text:
            return ""

        # 1. Unicode Compatibility Normalization
        text = unicodedata.normalize("NFKC", text)

        # 2. Normalize Line Endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Horizontal Whitespace Normalization (preserve newlines)
        text = re.sub(r"[ \t]+", " ", text)

        # 4. Remove excessive blank lines (allow at most one blank line between paragraphs, i.e., max 2 newlines)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 5. Trim leading and trailing whitespace
        return text.strip()
