from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.documents.domain.models import DocumentScope, DocumentStatus
from app.documents.infrastructure.persistence.models import SQLAlchemyDocument
from app.documents.services.ingestion_reaper import DurableIngestionReaper


@pytest.mark.asyncio
async def test_ingestion_reaper_recovers_stale_queued_documents():
    user_id = uuid4()
    stale_doc_id = uuid4()

    now = datetime.now(UTC)
    stale_time = now - timedelta(seconds=120)

    stale_doc = SQLAlchemyDocument(
        id=stale_doc_id,
        user_id=user_id,
        filename="stale.txt",
        original_filename="stale.txt",
        content_type="text/plain",
        file_size=100,
        checksum="chk_stale",
        scope=DocumentScope.LIBRARY.value,
        status=DocumentStatus.QUEUED.value,
        created_at=stale_time,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stale_doc]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    mock_session_factory.return_value = mock_session_ctx

    mock_queue = AsyncMock()

    reaper = DurableIngestionReaper(
        session_factory=mock_session_factory,
        task_queue=mock_queue,
        stale_threshold_seconds=60.0,
    )

    reaped_count = await reaper.reap()

    assert reaped_count == 1
    mock_queue.enqueue.assert_called_once_with(
        task_type="PROCESS_DOCUMENT",
        payload={
            "document_id": str(stale_doc_id),
            "user_id": str(user_id),
            "checksum": "chk_stale",
            "scope": DocumentScope.LIBRARY.value,
        },
        max_attempts=3,
    )
