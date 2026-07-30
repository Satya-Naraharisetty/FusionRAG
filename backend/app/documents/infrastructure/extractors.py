import io
import pathlib

import docx
from pypdf import PdfReader

from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType
from app.documents.domain.interfaces import DocumentExtractor
from app.documents.domain.models import ExtractionResult


class PDFExtractor(DocumentExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses text from PDF using pypdf.
        """
        if not file_bytes:
            raise DocumentCorrupted("PDF file is empty.")
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                raise DocumentCorrupted("PDF has 0 pages.")

            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""

            return ExtractionResult(text=text, page_count=len(reader.pages))
        except DocumentCorrupted:
            raise
        except Exception as e:
            raise DocumentCorrupted(
                f"Failed to parse PDF document. It may be corrupted: {e}"
            )


class DOCXExtractor(DocumentExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses text from Word docx paragraphs and tables.
        """
        if not file_bytes:
            raise DocumentCorrupted("DOCX file is empty.")
        try:
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
        except Exception as e:
            raise DocumentCorrupted(
                f"Failed to parse DOCX document. It may be corrupted: {e}"
            )


class TXTExtractor(DocumentExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses plain text using UTF-8 decoding.
        """
        try:
            text = file_bytes.decode("utf-8")
            return ExtractionResult(text=text, page_count=1)
        except UnicodeDecodeError as e:
            raise DocumentCorrupted(f"Text file is not valid UTF-8: {e}")


class MarkdownExtractor(DocumentExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """
        Parses markdown text using UTF-8 decoding.
        """
        try:
            text = file_bytes.decode("utf-8")
            return ExtractionResult(text=text, page_count=1)
        except UnicodeDecodeError as e:
            raise DocumentCorrupted(f"Markdown file is not valid UTF-8: {e}")


class ExtractorFactory:
    def __init__(self) -> None:
        self._extractors = {
            "application/pdf": PDFExtractor(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCXExtractor(),
            "text/plain": TXTExtractor(),
            "text/markdown": MarkdownExtractor(),
            "text/x-markdown": MarkdownExtractor(),
        }
        self._extension_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
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
