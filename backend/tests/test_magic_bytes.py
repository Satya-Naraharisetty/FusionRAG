import io
import zipfile

import pytest

from app.documents.domain.exceptions import DocumentCorrupted, UnsupportedDocumentType
from app.documents.services.validator import MagicByteValidator


def test_empty_file_rejected():
    with pytest.raises(DocumentCorrupted, match="empty"):
        MagicByteValidator.validate(b"", "sample.pdf")


def test_missing_extension_rejected():
    with pytest.raises(UnsupportedDocumentType, match="extension"):
        MagicByteValidator.validate(b"%PDF-1.4 dummy", "sample")


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedDocumentType, match="Unsupported file extension"):
        MagicByteValidator.validate(b"random content", "sample.xyz")


def test_valid_pdf():
    valid_pdf = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    # Should not raise
    MagicByteValidator.validate(valid_pdf, "document.pdf")


def test_invalid_pdf_disguised_binary():
    disguised_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    with pytest.raises(DocumentCorrupted, match="Invalid PDF file header"):
        MagicByteValidator.validate(disguised_exe, "malicious.pdf")


def test_valid_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<?xml version='1.0'?><Types></Types>")
        zf.writestr("word/document.xml", b"<?xml version='1.0'?><document></document>")
    docx_bytes = buf.getvalue()

    # Should not raise
    MagicByteValidator.validate(docx_bytes, "report.docx")


def test_invalid_docx_not_zip():
    fake_docx = b"This is just plain text saved as docx"
    with pytest.raises(DocumentCorrupted, match="Invalid DOCX file header"):
        MagicByteValidator.validate(fake_docx, "report.docx")


def test_invalid_docx_zip_without_word_structure():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("some_other_file.txt", b"hello world")
    zip_bytes = buf.getvalue()

    with pytest.raises(UnsupportedDocumentType, match="WordprocessingML"):
        MagicByteValidator.validate(zip_bytes, "archive_renamed.docx")


def test_docx_zip_bomb_detection():
    buf = io.BytesIO()
    # High compression ratio payload
    large_zeros = b"\x00" * (20 * 1024 * 1024)  # 20MB uncompressed
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<?xml version='1.0'?><Types></Types>")
        zf.writestr("word/document.xml", large_zeros)
    bomb_bytes = buf.getvalue()

    # Highly compressible stream will trip the expansion ratio check
    with pytest.raises(DocumentCorrupted, match="potential zip bomb"):
        MagicByteValidator.validate(bomb_bytes, "bomb.docx")


def test_valid_png():
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    MagicByteValidator.validate(valid_png, "image.png")


def test_invalid_png():
    with pytest.raises(DocumentCorrupted, match="Invalid PNG file header"):
        MagicByteValidator.validate(b"NOT_A_PNG_HEADER", "image.png")


def test_valid_jpeg():
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    MagicByteValidator.validate(valid_jpeg, "photo.jpg")
    MagicByteValidator.validate(valid_jpeg, "photo.jpeg")


def test_invalid_jpeg():
    with pytest.raises(DocumentCorrupted, match="Invalid JPEG file header"):
        MagicByteValidator.validate(b"\x00\x01\x02\x03FAKEJPEG", "photo.jpg")


def test_valid_webp():
    valid_webp = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00"
    MagicByteValidator.validate(valid_webp, "graphic.webp")


def test_invalid_webp():
    with pytest.raises(DocumentCorrupted, match="Invalid WEBP file header"):
        MagicByteValidator.validate(b"RIFF\x24\x00\x00\x00NOTWEBP", "graphic.webp")


def test_valid_text_and_markdown():
    valid_txt = b"Hello, world! This is valid UTF-8 plain text."
    MagicByteValidator.validate(valid_txt, "notes.txt")
    MagicByteValidator.validate(valid_txt, "readme.md")
    MagicByteValidator.validate(valid_txt, "doc.markdown")


def test_invalid_text_with_null_bytes():
    binary_disguised_as_txt = b"Hello\x00World\x00Binary\x00"
    with pytest.raises(DocumentCorrupted, match="Binary null bytes detected"):
        MagicByteValidator.validate(binary_disguised_as_txt, "disguised.txt")


def test_invalid_text_non_utf8():
    invalid_utf8 = b"\xff\xfe\x00\x00InvalidUTF8Sequence"
    # Will fail either on null byte check or utf-8 decode
    with pytest.raises(DocumentCorrupted):
        MagicByteValidator.validate(invalid_utf8, "bad_encoding.txt")
