import io
import logging
import pathlib
import zipfile

from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType

logger = logging.getLogger(__name__)


class MagicByteValidator:
    """
    Binary file signature (magic byte) validator.
    Inspects raw file bytes to verify genuine file formats before storage and processing.
    Protects against file extension spoofing, corrupted payloads, polyglot attacks, and zip bombs.
    """

    # Maximum decompression expansion factor allowed for archive-based formats (e.g. docx)
    MAX_ZIP_EXPANSION_RATIO = 100
    # Absolute ceiling for uncompressed docx content (default 250 MB)
    MAX_UNCOMPRESSED_DOCX_BYTES = 250 * 1024 * 1024

    @classmethod
    def validate(
        cls, file_bytes: bytes, filename: str, _content_type: str | None = None
    ) -> None:
        """
        Validates file content against expected magic bytes and structural rules for its extension.
        Raises UnsupportedDocumentType or DocumentCorrupted on validation failure.
        """
        if not file_bytes or len(file_bytes) == 0:
            raise DocumentCorrupted("Uploaded file is empty (0 bytes).")

        ext = pathlib.Path(filename.lower()).suffix
        if not ext:
            raise UnsupportedDocumentType("File must have a valid extension.")

        if ext == ".pdf":
            cls._validate_pdf(file_bytes)
        elif ext == ".docx":
            cls._validate_docx(file_bytes)
        elif ext in (".png",):
            cls._validate_png(file_bytes)
        elif ext in (".jpg", ".jpeg"):
            cls._validate_jpeg(file_bytes)
        elif ext == ".webp":
            cls._validate_webp(file_bytes)
        elif ext in (".txt", ".md", ".markdown"):
            cls._validate_text(file_bytes, ext)
        else:
            raise UnsupportedDocumentType(f"Unsupported file extension: '{ext}'")

    @classmethod
    def _validate_pdf(cls, data: bytes) -> None:
        if len(data) < 5 or not data.startswith(b"%PDF-"):
            raise DocumentCorrupted(
                "Invalid PDF file header: magic bytes '%PDF-' not found."
            )

    @classmethod
    def _validate_docx(cls, data: bytes) -> None:
        # 1. Check PK zip header
        if len(data) < 4 or not data.startswith(b"PK\x03\x04"):
            raise DocumentCorrupted(
                "Invalid DOCX file header: standard ZIP signature 'PK\x03\x04' not found."
            )

        # 2. Validate ZIP archive integrity & structure
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                namelist = zf.namelist()
                # Check required OpenXML components
                has_content_types = "[Content_Types].xml" in namelist
                has_word_dir = any(name.startswith("word/") for name in namelist)

                if not (has_content_types and has_word_dir):
                    raise UnsupportedDocumentType(
                        "File is a ZIP archive but does not contain valid WordprocessingML (DOCX) structure."
                    )

                # 3. Zip bomb & excessive decompression check
                total_uncompressed = 0
                for info in zf.infolist():
                    total_uncompressed += info.file_size
                    if total_uncompressed > cls.MAX_UNCOMPRESSED_DOCX_BYTES:
                        raise DocumentCorrupted(
                            "DOCX archive exceeds maximum allowable uncompressed size (potential zip bomb)."
                        )

                compressed_size = max(len(data), 1)
                if (total_uncompressed / compressed_size) > cls.MAX_ZIP_EXPANSION_RATIO and total_uncompressed > 10 * 1024 * 1024:
                    raise DocumentCorrupted(
                        "DOCX archive exhibits suspicious compression ratio (potential zip bomb)."
                    )

        except zipfile.BadZipFile as e:
            raise DocumentCorrupted(f"Corrupted DOCX zip archive: {e}") from e
        except (UnsupportedDocumentType, DocumentCorrupted):
            raise
        except Exception as e:
            raise DocumentCorrupted(f"Failed to inspect DOCX archive: {e}") from e

    @classmethod
    def _validate_png(cls, data: bytes) -> None:
        png_header = b"\x89PNG\r\n\x1a\n"
        if len(data) < 8 or not data.startswith(png_header):
            raise DocumentCorrupted("Invalid PNG file header: magic signature not found.")

    @classmethod
    def _validate_jpeg(cls, data: bytes) -> None:
        if len(data) < 3 or not data.startswith(b"\xff\xd8\xff"):
            raise DocumentCorrupted("Invalid JPEG file header: SOI marker '\\xff\\xd8\\xff' not found.")

    @classmethod
    def _validate_webp(cls, data: bytes) -> None:
        if len(data) < 12 or not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
            raise DocumentCorrupted("Invalid WEBP file header: RIFF/WEBP signature not found.")

    @classmethod
    def _validate_text(cls, data: bytes, ext: str) -> None:
        # Plain text must not contain binary NULL bytes in sample prefix
        sample = data[:4096]
        if b"\x00" in sample:
            raise DocumentCorrupted(
                f"Binary null bytes detected in text file with extension '{ext}'. Plain text expected."
            )

        try:
            data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise DocumentCorrupted(f"Text file with extension '{ext}' is not valid UTF-8: {e}") from e
