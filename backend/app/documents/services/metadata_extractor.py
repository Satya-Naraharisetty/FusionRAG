import logging

from langdetect import detect

from app.documents.domain.models import DocumentMetadata

logger = logging.getLogger(__name__)


class MetadataExtractor:
    def extract_metadata(
        self, text: str, page_count: int | None = None
    ) -> DocumentMetadata:
        """
        Calculates document metrics: word count and language.
        Language detection is run exactly once per document on the entire text.
        """
        cleaned_text = text.strip()
        word_count = len(cleaned_text.split()) if cleaned_text else 0

        # Language detection (once per document, not per chunk)
        language = "en"
        if cleaned_text:
            try:
                # Use a prefix of the text for faster language detection if the text is huge
                detect_input = cleaned_text[:10000]
                language = detect(detect_input)
            except Exception as e:
                logger.warning(f"Language detection failed, defaulting to 'en': {e}")
                language = "en"

        return DocumentMetadata(
            page_count=page_count, word_count=word_count, language=language
        )
