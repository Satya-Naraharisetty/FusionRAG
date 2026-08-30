import asyncio
import base64
import io
import logging
import pathlib

import docx
import httpx
from pypdf import PdfReader

try:
    import pypdfium2
except ImportError:
    pypdfium2 = None  # type: ignore[assignment]

from app.core.config import settings
from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType
from app.documents.domain.interfaces import DocumentExtractor
from app.documents.domain.models import ExtractionResult

logger = logging.getLogger(__name__)


class PDFExtractor(DocumentExtractor):
    def __init__(self, min_text_chars_per_page: int = 30) -> None:
        self.min_text_chars_per_page = min_text_chars_per_page
        self._ocr_semaphore = asyncio.Semaphore(5)

    async def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses text from PDF. If a page contains sparse or no digital text
        (e.g. scanned handwritten notes or image-only pages), it automatically
        rasterizes the page via pypdfium2 (with pypdf.images fallback) and runs
        Gemini Multimodal Vision OCR.
        """
        if not file_bytes:
            raise DocumentCorrupted("PDF file is empty.")

        def _parse_pages():
            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                raise DocumentCorrupted("PDF has 0 pages.")

            pages_data = []
            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                needs_ocr = len(page_text.strip()) < self.min_text_chars_per_page
                pages_data.append(
                    {
                        "index": idx,
                        "text": page_text,
                        "needs_ocr": needs_ocr,
                    }
                )
            return len(reader.pages), pages_data

        try:
            page_count, pages_data = await asyncio.to_thread(_parse_pages)
        except DocumentCorrupted:
            raise
        except Exception as e:
            raise DocumentCorrupted(
                f"Failed to parse PDF document. It may be corrupted: {e}"
            ) from e

        # Check if any pages need OCR and if API key is present
        api_key = settings.get_gemini_llm_api_key()
        pages_needing_ocr = [p for p in pages_data if p["needs_ocr"]]

        if pages_needing_ocr and api_key:

            async def _process_page_ocr(page_info: dict) -> tuple[int, str]:
                page_idx = page_info["index"]
                image_bytes = await self._render_or_extract_page_image(
                    file_bytes, page_idx
                )
                if not image_bytes:
                    return page_idx, page_info["text"]

                prompt = (
                    "Analyze this document page. Extract all handwritten notes, printed text, "
                    "mathematical expressions, diagrams, tables, and margin notes word-for-word (OCR). "
                    "Output only the verbatim extracted text clearly without conversational filler."
                )
                try:
                    async with self._ocr_semaphore:
                        ocr_text = await self._extract_ocr_via_gemini(
                            image_bytes, "image/png", prompt, api_key
                        )
                    combined = (
                        f"{page_info['text'].strip()}\n{ocr_text.strip()}".strip()
                        if page_info["text"].strip()
                        else ocr_text.strip()
                    )
                    return page_idx, combined
                except Exception as ocr_err:
                    logger.warning(
                        f"OCR failed for PDF page {page_idx + 1}: {ocr_err}. Falling back to raw text."
                    )
                    return page_idx, page_info["text"]

            ocr_results = await asyncio.gather(
                *[_process_page_ocr(p) for p in pages_needing_ocr],
                return_exceptions=False,
            )
            ocr_map = dict(ocr_results)
            final_pages_text = [ocr_map.get(p["index"], p["text"]) for p in pages_data]
        else:
            final_pages_text = [p["text"] for p in pages_data]

        full_text = "".join(final_pages_text)
        return ExtractionResult(text=full_text, page_count=page_count)

    async def _render_or_extract_page_image(
        self, file_bytes: bytes, page_idx: int
    ) -> bytes | None:
        def _render():
            # Primary: pypdfium2 full-page rasterization (Google PDFium engine)
            if pypdfium2 is not None:
                try:
                    pdf = pypdfium2.PdfDocument(file_bytes)
                    page = pdf[page_idx]
                    # Render at scale=2 (approx 150 DPI) for crisp handwriting recognition with low RAM footprint
                    pil_img = page.render(scale=2).to_pil()
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception as err:
                    logger.debug(
                        f"pypdfium2 rendering failed on page {page_idx}: {err}. Trying pypdf fallback."
                    )

            # Fallback: pypdf page.images extraction
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                page = reader.pages[page_idx]
                if page.images and len(page.images) > 0:
                    return page.images[0].data
            except Exception as err:
                logger.debug(f"pypdf image extraction failed on page {page_idx}: {err}")

            return None

        return await asyncio.to_thread(_render)

    async def _extract_ocr_via_gemini(
        self, image_bytes: bytes, mime_type: str, prompt: str, api_key: str
    ) -> str:
        base64_data = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048},
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"

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

        api_key = settings.get_gemini_llm_api_key()
        if not api_key:
            raise UnsupportedDocumentType(
                "GEMINI_LLM_API_KEY (or GEMINI_API_KEY) is required for image vision processing."
            )

        prompt = (
            "Analyze the attached image. Extract all readable text word-for-word (OCR). "
            "Then, provide a detailed description of any charts, diagrams, tables, figures, or visual structures in the image. "
            "Do not include conversational filler in your response; output only the extracted text and the semantic description."
        )

        try:
            extracted_text = await self._extract_via_gemini(file_bytes, prompt, api_key)
        except Exception as e:
            logger.error(f"Failed to extract image content via Gemini: {e}")
            raise DocumentCorrupted(f"Gemini image extraction failed: {e}") from e

        return ExtractionResult(text=extracted_text, page_count=1)

    async def _extract_via_gemini(
        self, file_bytes: bytes, prompt: str, api_key: str
    ) -> str:
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"

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
