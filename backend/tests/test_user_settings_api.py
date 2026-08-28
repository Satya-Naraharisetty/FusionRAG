from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import status

from app.api.dependencies import get_current_user_context, get_db
from app.auth.infrastructure.persistence.models import SQLAlchemyUserSettings
from app.auth.services.user_settings_service import UserSettingsService
from app.main import app


@pytest.mark.asyncio
async def test_get_and_patch_user_settings(client):
    user_id = uuid4()
    now = datetime.now(UTC)

    mock_context = {
        "user_id": str(user_id),
        "email": f"user_{str(user_id)[:8]}@example.com",
        "role": "user",
    }

    mock_settings = SQLAlchemyUserSettings(
        user_id=user_id,
        folders=[
            {"id": "folder-general", "name": "General", "conversationIds": []},
            {"id": "folder-research", "name": "Research", "conversationIds": []},
        ],
        pinned_conversations=[],
        conversation_tags={},
        document_folders=[],
        document_folder_mappings={},
        document_custom_order=[],
        document_filter_presets=[],
        preferences={},
        created_at=now,
        updated_at=now,
    )

    async def mock_get_or_create(db, uid):
        return mock_settings

    async def mock_update(db, uid, patch):
        if patch.folders is not None:
            mock_settings.folders = patch.folders
        if patch.pinned_conversations is not None:
            mock_settings.pinned_conversations = patch.pinned_conversations
        if patch.conversation_tags is not None:
            mock_settings.conversation_tags = patch.conversation_tags
        if patch.document_folders is not None:
            mock_settings.document_folders = patch.document_folders
        if patch.document_folder_mappings is not None:
            mock_settings.document_folder_mappings = patch.document_folder_mappings
        if patch.preferences is not None:
            mock_settings.preferences = patch.preferences
        return mock_settings

    UserSettingsService.get_or_create = mock_get_or_create  # type: ignore
    UserSettingsService.update = mock_update  # type: ignore

    app.dependency_overrides[get_current_user_context] = lambda: mock_context
    app.dependency_overrides[get_db] = lambda: AsyncMock()

    try:
        # GET default settings
        res = client.get("/api/v1/user/settings")
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["user_id"] == str(user_id)
        assert len(data["folders"]) == 2
        assert data["pinned_conversations"] == []
        assert data["conversation_tags"] == {}

        # PATCH update settings
        new_folders = [
            {"id": "f1", "name": "Work", "conversationIds": ["c1", "c2"]},
            {"id": "f2", "name": "Personal", "conversationIds": []},
        ]
        new_pins = ["c1"]
        new_tags = {"c1": [{"name": "Important", "color": "bg-red-500"}]}
        new_doc_folders = [{"id": "df1", "name": "Invoices"}]
        new_doc_mappings = {"d1": "df1"}
        new_prefs = {"theme": "dark", "sidebarCollapsed": False}

        patch_res = client.patch(
            "/api/v1/user/settings",
            json={
                "folders": new_folders,
                "pinned_conversations": new_pins,
                "conversation_tags": new_tags,
                "document_folders": new_doc_folders,
                "document_folder_mappings": new_doc_mappings,
                "preferences": new_prefs,
            },
        )
        assert patch_res.status_code == status.HTTP_200_OK
        updated_data = patch_res.json()
        assert updated_data["folders"] == new_folders
        assert updated_data["pinned_conversations"] == new_pins
        assert updated_data["conversation_tags"] == new_tags
        assert updated_data["document_folders"] == new_doc_folders
        assert updated_data["document_folder_mappings"] == new_doc_mappings
        assert updated_data["preferences"]["theme"] == "dark"

        # GET again to verify persistence
        res2 = client.get("/api/v1/user/settings")
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        assert data2["folders"] == new_folders
        assert data2["pinned_conversations"] == new_pins
    finally:
        app.dependency_overrides.clear()
