import asyncio
import base64
import io
import logging
import pathlib

import docx
import httpx
from pypdf import PdfReader

from app.core.config import settings
from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType
from app.documents.domain.interfaces import DocumentExtractor
from app.documents.domain.models import ExtractionResult

logger = logging.getLogger(__name__)


class PDFExtractor(DocumentExtractor):
    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses text from PDF using pypdf inside a thread pool.
        """
        if not file_bytes:
            raise DocumentCorrupted("PDF file is empty.")

        def _parse():
            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                raise DocumentCorrupted("PDF has 0 pages.")

            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""

            return ExtractionResult(text=text, page_count=len(reader.pages))

        try:
            return await asyncio.to_thread(_parse)
        except DocumentCorrupted:
            raise
        except Exception as e:
            raise DocumentCorrupted(
                f"Failed to parse PDF document. It may be corrupted: {e}"
            )


class DOCXExtractor(DocumentExtractor):
    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses text from Word docx paragraphs and tables inside a thread pool.
        """
        if not file_bytes:
            raise DocumentCorrupted("DOCX file is empty.")

        def _parse():
            doc = docx.Document(io.BytesIO(file_bytes))

            # Read paragraphs
            paragraphs_text = []
            for paragraph in doc.paragraphs:
                if paragraph.text:
                    paragraphs_text.append(paragraph.text)

            # Read tables
            table_text = []
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells if cell.text]
                    if row_text:
                        table_text.append(" | ".join(row_text))

            full_text = "\n".join(paragraphs_text)
            if table_text:
                full_text += "\n\n" + "\n".join(table_text)

            return ExtractionResult(
                text=full_text,
                page_count=1,  # DOCX does not explicitly store page count
            )

        try:
            return await asyncio.to_thread(_parse)
        except Exception as e:
            raise DocumentCorrupted(
                f"Failed to parse DOCX document. It may be corrupted: {e}"
            )


class TXTExtractor(DocumentExtractor):
    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses plain text using UTF-8 decoding.
        """
        try:
            text = file_bytes.decode("utf-8")
            return ExtractionResult(text=text, page_count=1)
        except UnicodeDecodeError as e:
            raise DocumentCorrupted(f"Text file is not valid UTF-8: {e}")


class MarkdownExtractor(DocumentExtractor):
    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses markdown text using UTF-8 decoding.
        """
        try:
            text = file_bytes.decode("utf-8")
            return ExtractionResult(text=text, page_count=1)
        except UnicodeDecodeError as e:
            raise DocumentCorrupted(f"Markdown file is not valid UTF-8: {e}")


class ImageExtractor(DocumentExtractor):
    def __init__(self, mime_type: str) -> None:
        self.mime_type = mime_type

    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Uses Google Gemini Vision to extract text and describe the image.
        """
        if not file_bytes:
            raise DocumentCorrupted("Image file is empty.")

        if not settings.GEMINI_API_KEY:
            raise UnsupportedDocumentType(
                "GEMINI_API_KEY is required for image vision processing."
            )

        prompt = (
            "Analyze the attached image. Extract all readable text word-for-word (OCR). "
            "Then, provide a detailed description of any charts, diagrams, tables, figures, or visual structures in the image. "
            "Do not include conversational filler in your response; output only the extracted text and the semantic description."
        )

        try:
            extracted_text = await self._extract_via_gemini(file_bytes, prompt)
        except Exception as e:
            logger.error(f"Failed to extract image content via Gemini: {e}")
            raise DocumentCorrupted(f"Gemini image extraction failed: {e}") from e

        return ExtractionResult(text=extracted_text, page_count=1)

    async def _extract_via_gemini(self, file_bytes: bytes, prompt: str) -> str:
        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": self.mime_type,
                                "data": base64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048},
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                raise RuntimeError(
                    f"Unexpected response structure from Gemini API: {e}"
                ) from e


class ExtractorFactory:
    def __init__(self) -> None:
        self._extractors = {
            "application/pdf": PDFExtractor(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCXExtractor(),
            "text/plain": TXTExtractor(),
            "text/markdown": MarkdownExtractor(),
            "text/x-markdown": MarkdownExtractor(),
            "image/png": ImageExtractor("image/png"),
            "image/jpeg": ImageExtractor("image/jpeg"),
            "image/webp": ImageExtractor("image/webp"),
        }
        self._extension_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

    def get_extractor(self, content_type: str, filename: str) -> DocumentExtractor:
        """
        Returns the appropriate DocumentExtractor strategy based on content_type and filename extension.
        """
        mime = content_type.lower().strip()
        ext = pathlib.Path(filename.lower()).suffix

        resolved_mime = self._extension_map.get(ext)
        if not resolved_mime:
            raise UnsupportedDocumentType(f"Unsupported file extension: {ext}")

        if mime in self._extractors:
            return self._extractors[mime]

        if resolved_mime in self._extractors:
            return self._extractors[resolved_mime]

        raise UnsupportedDocumentType(f"Unsupported document MIME type: {content_type}")
