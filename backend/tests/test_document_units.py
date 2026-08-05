import uuid
from unittest.mock import MagicMock, patch

import boto3
import pytest
from app.documents.domain.exceptions import (
    DocumentCorrupted,
    InvalidStateTransitionException,
    UnsupportedDocumentType,
)
from app.documents.domain.models import (
    DocumentStateMachine,
    DocumentStatus,
)
from app.documents.infrastructure.checksum import SHA256ChecksumGenerator
from app.documents.infrastructure.extractors import (
    DOCXExtractor,
    ExtractorFactory,
    MarkdownExtractor,
    PDFExtractor,
    TXTExtractor,
)
from app.documents.infrastructure.storage import LocalStorageProvider, S3StorageProvider
from app.documents.services.chunking import ChunkingService
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner
from moto import mock_aws

# --- State Machine Tests ---


def test_state_machine_valid_transitions():
    # QUEUED -> PROCESSING
    DocumentStateMachine.validate_transition(
        DocumentStatus.QUEUED, DocumentStatus.PROCESSING
    )
    # PROCESSING -> COMPLETED
    DocumentStateMachine.validate_transition(
        DocumentStatus.PROCESSING, DocumentStatus.COMPLETED
    )
    # PROCESSING -> FAILED
    DocumentStateMachine.validate_transition(
        DocumentStatus.PROCESSING, DocumentStatus.FAILED
    )
    # COMPLETED -> QUEUED
    DocumentStateMachine.validate_transition(
        DocumentStatus.COMPLETED, DocumentStatus.QUEUED
    )
    # FAILED -> QUEUED
    DocumentStateMachine.validate_transition(
        DocumentStatus.FAILED, DocumentStatus.QUEUED
    )
    # Identical state transition is no-op
    DocumentStateMachine.validate_transition(
        DocumentStatus.QUEUED, DocumentStatus.QUEUED
    )


def test_state_machine_invalid_transitions():
    with pytest.raises(InvalidStateTransitionException):
        DocumentStateMachine.validate_transition(
            DocumentStatus.QUEUED, DocumentStatus.COMPLETED
        )

    with pytest.raises(InvalidStateTransitionException):
        DocumentStateMachine.validate_transition(
            DocumentStatus.COMPLETED, DocumentStatus.COMPLETED
        )  # wait, identical transitions are allowed in code, but let's test a distinct invalid one
        DocumentStateMachine.validate_transition(
            DocumentStatus.COMPLETED, DocumentStatus.FAILED
        )


# --- Text Cleaner Tests ---


def test_text_cleaner():
    cleaner = TextCleaner()
    # Unicode compatibility
    assert cleaner.clean("Héllo\u00a0World") == "Héllo World"
    # Line endings
    assert cleaner.clean("Line 1\r\nLine 2\rLine 3") == "Line 1\nLine 2\nLine 3"
    # Horizontal whitespace
    assert cleaner.clean("Word1   \t  Word2") == "Word1 Word2"
    # Excessive blank lines
    assert cleaner.clean("Para 1\n\n\n\nPara 2") == "Para 1\n\nPara 2"
    # Edge case: empty/None
    assert cleaner.clean("") == ""


# --- Metadata Extractor Tests ---


@patch("app.documents.services.metadata_extractor.detect")
def test_metadata_extractor(mock_detect):
    mock_detect.return_value = "fr"
    extractor = MetadataExtractor()

    text = "Bonjour tout le monde. Ceci est un texte en français."
    meta = extractor.extract_metadata(text, page_count=5)

    assert meta.page_count == 5
    assert meta.word_count == 10
    assert meta.language == "fr"
    mock_detect.assert_called_once()


@patch("app.documents.services.metadata_extractor.detect")
def test_metadata_extractor_language_fallback(mock_detect):
    mock_detect.side_effect = Exception("error")
    extractor = MetadataExtractor()

    meta = extractor.extract_metadata("Short text", page_count=None)
    assert meta.language == "en"
    assert meta.word_count == 2


# --- Checksum Generator Tests ---


def test_checksum_generator():
    generator = SHA256ChecksumGenerator()
    content = b"hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert generator.generate(content) == expected


# --- Storage Provider Tests ---


def test_local_storage_provider(tmp_path):
    storage = LocalStorageProvider(upload_dir=str(tmp_path))
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    filename = "test_doc.txt"
    content = b"Hello Storage"

    # Save
    key = storage.save(filename, content, user_id, doc_id)
    assert key == f"user_{user_id}/{doc_id}.txt"

    # Get
    assert storage.get(key) == content

    # Delete
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.get(key)


# --- Chunker Tests ---


def test_chunking_service():
    chunker = ChunkingService(chunk_size=20, chunk_overlap=5, min_chunk_size=3)
    text = "Paragraph one here.\n\nParagraph two here.\n\nShort."
    doc_id = uuid.uuid4()

    result = chunker.chunk_document(text, doc_id)
    chunks = result.chunks

    assert len(chunks) > 0
    for idx, c in enumerate(chunks):
        assert c.document_id == doc_id
        assert c.chunk_index == idx
        assert len(c.text) <= chunker.chunk_size
        assert c.token_estimate == len(c.text) // 4
        # Validate indices match substring
        assert text[c.character_start : c.character_end] == c.text


def test_chunking_service_min_size():
    chunker = ChunkingService(chunk_size=50, chunk_overlap=10, min_chunk_size=20)
    # Substring is smaller than min size
    text = "Long text here that is large enough.\n\nShort."
    result = chunker.chunk_document(text, uuid.uuid4())
    # Should exclude the "Short." chunk if it falls under 20 characters and there are multiple chunks
    assert not any(c.text == "Short." for c in result.chunks)


# --- Extractor Strategy Tests ---


@patch("app.documents.infrastructure.extractors.PdfReader")
def test_pdf_extractor(mock_pdf_reader):
    # Setup mock
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF Page Text"
    mock_pdf_reader.return_value.pages = [mock_page, mock_page]

    extractor = PDFExtractor()
    res = extractor.extract(b"dummy pdf bytes")

    assert res.text == "PDF Page TextPDF Page Text"
    assert res.page_count == 2


@patch("app.documents.infrastructure.extractors.docx.Document")
def test_docx_extractor(mock_docx_doc):
    # Setup mock
    mock_para = MagicMock()
    mock_para.text = "Para Text"
    mock_docx_doc.return_value.paragraphs = [mock_para]

    mock_cell = MagicMock()
    mock_cell.text = "Cell Text"
    mock_row = MagicMock()
    mock_row.cells = [mock_cell]
    mock_table = MagicMock()
    mock_table.rows = [mock_row]
    mock_docx_doc.return_value.tables = [mock_table]

    extractor = DOCXExtractor()
    res = extractor.extract(b"dummy docx bytes")

    assert "Para Text" in res.text
    assert "Cell Text" in res.text
    assert res.page_count == 1


def test_txt_extractor():
    extractor = TXTExtractor()
    res = extractor.extract(b"Plain text content")
    assert res.text == "Plain text content"
    assert res.page_count == 1

    with pytest.raises(DocumentCorrupted):
        extractor.extract(b"\x80abc")  # invalid utf-8


def test_markdown_extractor():
    extractor = MarkdownExtractor()
    res = extractor.extract(b"# Header\n\nContent")
    assert res.text == "# Header\n\nContent"
    assert res.page_count == 1


def test_extractor_factory():
    factory = ExtractorFactory()

    # Get PDF extractor
    assert isinstance(factory.get_extractor("application/pdf", "doc.pdf"), PDFExtractor)
    # Mime case insensitivity and whitespace handling
    assert isinstance(
        factory.get_extractor(" APPLICATION/PDF ", "doc.pdf"), PDFExtractor
    )
    # Extensions matching
    assert isinstance(
        factory.get_extractor("application/octet-stream", "doc.txt"), TXTExtractor
    )

    with pytest.raises(UnsupportedDocumentType):
        factory.get_extractor("application/unknown", "doc.unknown")


@mock_aws
def test_s3_storage_provider():
    # Setup mock S3 environment
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    # Verify connection
    storage = S3StorageProvider(bucket_name="test-bucket", region_name="us-east-1")
    storage.verify_connection()
    storage.verify_write_access()

    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    filename = "test.txt"
    content = b"Hello S3"

    # Save
    key = storage.save(filename, content, user_id, doc_id)
    assert key == f"user_{user_id}/{doc_id}.txt"

    # Get
    assert storage.get(key) == content

    # Generate presigned URLs
    upload_url = storage.generate_presigned_upload_url(key)
    assert "test-bucket" in upload_url
    assert key in upload_url

    download_url = storage.generate_presigned_download_url(key)
    assert "test-bucket" in download_url
    assert key in download_url

    # Delete
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.get(key)
