import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

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
    ImageExtractor,
    MarkdownExtractor,
    PDFExtractor,
    TXTExtractor,
)
from app.documents.infrastructure.storage import LocalStorageProvider
from app.documents.services.chunking import ChunkingService
from app.documents.services.metadata_extractor import MetadataExtractor
from app.documents.services.text_cleaner import TextCleaner

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
        # identical transitions are allowed in code, but let's test a distinct invalid one
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


@pytest.mark.asyncio
async def test_local_storage_provider(tmp_path):
    storage = LocalStorageProvider(upload_dir=str(tmp_path))
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    filename = "test_doc.txt"
    content = b"Hello Storage"

    # Save
    key = await storage.save(filename, content, user_id, doc_id)
    assert key == f"user_{user_id}/{doc_id}.txt"

    # Get
    assert await storage.get(key) == content

    # Delete
    await storage.delete(key)
    with pytest.raises(FileNotFoundError):
        await storage.get(key)


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
    text = "Long text here that is large enough.\n\nShort."
    result = chunker.chunk_document(text, uuid.uuid4())
    # Should exclude the "Short." chunk if it falls under 20 characters and there are multiple chunks
    assert not any(c.text == "Short." for c in result.chunks)


# --- Extractor Strategy Tests ---


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.PdfReader")
async def test_pdf_extractor(mock_pdf_reader):
    # Setup mock
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF Page Text"
    mock_pdf_reader.return_value.pages = [mock_page, mock_page]

    extractor = PDFExtractor()
    res = await extractor.extract(b"dummy pdf bytes")

    assert res.text == "PDF Page TextPDF Page Text"
    assert res.page_count == 2


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.PdfReader")
@patch("app.documents.infrastructure.extractors.pypdfium2")
@patch("app.documents.infrastructure.extractors.httpx.AsyncClient")
async def test_pdf_extractor_scanned_ocr_pypdfium2(
    mock_client_cls, mock_pdfium, mock_pdf_reader
):
    # Setup mock for page with sparse text (e.g. scanned handwritten page)
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""  # No digital text
    mock_pdf_reader.return_value.pages = [mock_page]

    # Setup pypdfium2 mock
    mock_pdfium_doc = MagicMock()
    mock_pdfium_page = MagicMock()
    mock_pil_img = MagicMock()
    mock_pil_img.save.side_effect = lambda buf, **_kwargs: buf.write(
        b"fake_rendered_png_bytes"
    )
    mock_pdfium_page.render.return_value.to_pil.return_value = mock_pil_img
    mock_pdfium_doc.__getitem__.return_value = mock_pdfium_page
    mock_pdfium.PdfDocument.return_value = mock_pdfium_doc

    # Setup httpx Gemini OCR response
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Handwritten math formula: E = mc^2"}]}}
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    with patch("app.documents.infrastructure.extractors.settings") as mock_settings:
        mock_settings.get_gemini_llm_api_key.return_value = "mock_key"
        extractor = PDFExtractor()
        res = await extractor.extract(b"dummy handwritten pdf bytes")

        assert res.page_count == 1
        assert "Handwritten math formula: E = mc^2" in res.text


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.PdfReader")
@patch("app.documents.infrastructure.extractors.pypdfium2", None)
@patch("app.documents.infrastructure.extractors.httpx.AsyncClient")
async def test_pdf_extractor_fallback_pypdf_images(mock_client_cls, mock_pdf_reader):
    # Setup mock page with sparse text and embedded scan image
    mock_img = MagicMock()
    mock_img.data = b"raw image bytes"
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_page.images = [mock_img]
    mock_pdf_reader.return_value.pages = [mock_page]

    # Setup httpx Gemini OCR response
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Handwritten notes: Meeting at 3 PM"}]}}
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    with patch("app.documents.infrastructure.extractors.settings") as mock_settings:
        mock_settings.get_gemini_llm_api_key.return_value = "mock_key"
        extractor = PDFExtractor()
        res = await extractor.extract(b"dummy pdf bytes with embedded image")

        assert res.page_count == 1
        assert "Handwritten notes: Meeting at 3 PM" in res.text


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.PdfReader")
@patch("app.documents.infrastructure.extractors.pypdfium2")
@patch("app.documents.infrastructure.extractors.httpx.AsyncClient")
async def test_pdf_extractor_mixed_digital_and_handwritten(
    mock_client_cls, mock_pdfium, mock_pdf_reader
):
    # Page 1: Digital text (length > 30 chars)
    page_1 = MagicMock()
    page_1.extract_text.return_value = (
        "This is a full digital paragraph with more than thirty characters of text."
    )

    # Page 2: Handwritten scan (length < 30 chars)
    page_2 = MagicMock()
    page_2.extract_text.return_value = ""

    mock_pdf_reader.return_value.pages = [page_1, page_2]

    # Setup pypdfium2 mock
    mock_pdfium_doc = MagicMock()
    mock_pdfium_page = MagicMock()
    mock_pil_img = MagicMock()
    mock_pil_img.save.side_effect = lambda buf, **_kwargs: buf.write(
        b"fake_rendered_png_bytes"
    )
    mock_pdfium_page.render.return_value.to_pil.return_value = mock_pil_img
    mock_pdfium_doc.__getitem__.return_value = mock_pdfium_page
    mock_pdfium.PdfDocument.return_value = mock_pdfium_doc

    # Setup httpx Gemini OCR response
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Handwritten annotations on page 2"}]}}
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value.__aenter__.return_value = mock_client

    with patch("app.documents.infrastructure.extractors.settings") as mock_settings:
        mock_settings.get_gemini_llm_api_key.return_value = "mock_key"
        extractor = PDFExtractor()
        res = await extractor.extract(b"dummy mixed pdf bytes")

        assert res.page_count == 2
        assert "This is a full digital paragraph" in res.text
        assert "Handwritten annotations on page 2" in res.text


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.docx.Document")
async def test_docx_extractor(mock_docx_doc):
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
    res = await extractor.extract(b"dummy docx bytes")

    assert "Para Text" in res.text
    assert "Cell Text" in res.text
    assert res.page_count == 1


@pytest.mark.asyncio
async def test_txt_extractor():
    extractor = TXTExtractor()
    res = await extractor.extract(b"Plain text content")
    assert res.text == "Plain text content"
    assert res.page_count == 1

    with pytest.raises(DocumentCorrupted):
        await extractor.extract(b"\x80abc")  # invalid utf-8


@pytest.mark.asyncio
async def test_markdown_extractor():
    extractor = MarkdownExtractor()
    res = await extractor.extract(b"# Header\n\nContent")
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


# --- Image Extractor Tests ---


@pytest.mark.asyncio
@patch("app.documents.infrastructure.extractors.httpx.AsyncClient")
async def test_image_extractor_gemini(mock_client_class):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Extracted text and chart details from Gemini"}]
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client_class.return_value.__aenter__.return_value = mock_client

    with patch("app.documents.infrastructure.extractors.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = "mock-gemini-key"
        mock_settings.get_gemini_llm_api_key.return_value = "mock-gemini-key"

        extractor = ImageExtractor("image/png")
        res = await extractor.extract(b"dummy png bytes")

        assert res.text == "Extracted text and chart details from Gemini"
        assert res.page_count == 1

        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert "gemini-3.5-flash" in args[0]

        assert "mock-gemini-key" in args[0]


@pytest.mark.asyncio
async def test_image_extractor_missing_key():
    with patch("app.documents.infrastructure.extractors.settings") as mock_settings:
        mock_settings.GEMINI_API_KEY = ""
        mock_settings.get_gemini_llm_api_key.return_value = ""

        extractor = ImageExtractor("image/jpeg")
        with pytest.raises(UnsupportedDocumentType):
            await extractor.extract(b"dummy jpeg bytes")


def test_image_extractor_factory():
    factory = ExtractorFactory()
    assert isinstance(factory.get_extractor("image/png", "chart.png"), ImageExtractor)
    assert isinstance(
        factory.get_extractor("application/octet-stream", "screenshot.jpg"),
        ImageExtractor,
    )


# --- DocumentService Replace Unit Tests ---


@pytest.mark.asyncio
async def test_replace_document_empty_file_rejected():
    from app.documents.services.document_service import DocumentService

    doc_service = DocumentService(
        document_repo=AsyncMock(),
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    with pytest.raises(DocumentCorrupted, match="empty"):
        await doc_service.replace_document_content(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            file_bytes=b"",
            original_filename="test.txt",
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_replace_document_file_too_large_rejected():
    from app.documents.domain.exceptions import DocumentTooLarge
    from app.documents.services.document_service import DocumentService

    doc_service = DocumentService(
        document_repo=AsyncMock(),
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=10,
    )

    with pytest.raises(DocumentTooLarge, match="exceeds maximum limit"):
        await doc_service.replace_document_content(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            file_bytes=b"123456789012345",
            original_filename="test.txt",
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_replace_document_unsupported_type_rejected():
    from app.documents.services.document_service import DocumentService

    doc_service = DocumentService(
        document_repo=AsyncMock(),
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    with pytest.raises(UnsupportedDocumentType):
        await doc_service.replace_document_content(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            file_bytes=b"MZ executable header",
            original_filename="malicious.exe",
            content_type="application/x-msdownload",
        )


@pytest.mark.asyncio
async def test_replace_document_concurrent_processing_rejected():
    from datetime import datetime

    from app.documents.domain.exceptions import DocumentProcessingInProgressException
    from app.documents.domain.models import Document, DocumentScope
    from app.documents.services.document_service import DocumentService

    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_repo = AsyncMock()
    mock_repo.get_by_id_for_update.return_value = Document(
        id=doc_id,
        user_id=user_id,
        scope=DocumentScope.LIBRARY,
        conversation_id=None,
        filename=f"user_{user_id}/{doc_id}.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=100,
        checksum="old_hash",
        status=DocumentStatus.PROCESSING,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    doc_service = DocumentService(
        document_repo=mock_repo,
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    with pytest.raises(DocumentProcessingInProgressException, match="processing"):
        await doc_service.replace_document_content(
            id=doc_id,
            user_id=user_id,
            file_bytes=b"new content",
            original_filename="test.txt",
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_replace_document_same_checksum_is_noop():
    from datetime import datetime

    from app.documents.domain.models import Document, DocumentScope
    from app.documents.services.document_service import DocumentService

    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    file_bytes = b"identical content bytes"
    checksum = SHA256ChecksumGenerator().generate(file_bytes)

    existing_doc = Document(
        id=doc_id,
        user_id=user_id,
        scope=DocumentScope.LIBRARY,
        conversation_id=None,
        filename=f"user_{user_id}/{doc_id}.txt",
        original_filename="test.txt",
        content_type="text/plain",
        file_size=len(file_bytes),
        checksum=checksum,
        status=DocumentStatus.COMPLETED,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_repo = AsyncMock()
    mock_repo.get_by_id_for_update.return_value = existing_doc
    mock_storage = AsyncMock()
    mock_task_queue = AsyncMock()
    mock_uow = AsyncMock()

    doc_service = DocumentService(
        document_repo=mock_repo,
        storage_provider=mock_storage,
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=mock_task_queue,
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=mock_uow,
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    res = await doc_service.replace_document_content(
        id=doc_id,
        user_id=user_id,
        file_bytes=file_bytes,
        original_filename="test.txt",
        content_type="text/plain",
    )

    assert res.id == doc_id
    assert res.checksum == checksum
    mock_storage.save.assert_not_called()
    mock_task_queue.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_replace_document_duplicate_other_doc_rejected():
    from datetime import datetime

    from app.documents.domain.exceptions import DuplicateDocumentException
    from app.documents.domain.models import Document, DocumentScope
    from app.documents.services.document_service import DocumentService

    doc_id = uuid.uuid4()
    other_doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    file_bytes = b"content already in library"
    checksum = SHA256ChecksumGenerator().generate(file_bytes)

    current_doc = Document(
        id=doc_id,
        user_id=user_id,
        scope=DocumentScope.LIBRARY,
        conversation_id=None,
        filename=f"user_{user_id}/{doc_id}.txt",
        original_filename="doc1.txt",
        content_type="text/plain",
        file_size=10,
        checksum="old_different_hash",
        status=DocumentStatus.COMPLETED,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    other_doc = Document(
        id=other_doc_id,
        user_id=user_id,
        scope=DocumentScope.LIBRARY,
        conversation_id=None,
        filename=f"user_{user_id}/{other_doc_id}.txt",
        original_filename="doc2.txt",
        content_type="text/plain",
        file_size=len(file_bytes),
        checksum=checksum,
        status=DocumentStatus.COMPLETED,
        extractor_version="v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_repo = AsyncMock()
    mock_repo.get_by_id_for_update.return_value = current_doc
    mock_repo.get_by_checksum_and_user.return_value = other_doc

    doc_service = DocumentService(
        document_repo=mock_repo,
        storage_provider=AsyncMock(),
        extractor_factory=ExtractorFactory(),
        checksum_generator=SHA256ChecksumGenerator(),
        task_queue=AsyncMock(),
        document_processing_service=AsyncMock(),
        embedding_service=AsyncMock(),
        uow=AsyncMock(),
        uuid_generator=AsyncMock(),
        time_provider=AsyncMock(),
        max_upload_size=1024,
    )

    with pytest.raises(
        DuplicateDocumentException, match="already exists in your library"
    ):
        await doc_service.replace_document_content(
            id=doc_id,
            user_id=user_id,
            file_bytes=file_bytes,
            original_filename="doc1.txt",
            content_type="text/plain",
        )
