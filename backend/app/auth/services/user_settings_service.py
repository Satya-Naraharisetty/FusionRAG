from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.domain.schemas import (
    UserSettingsPatchSchema,
)
from app.auth.infrastructure.persistence.models import SQLAlchemyUserSettings

DEFAULT_FOLDERS = [
    {"id": "folder-general", "name": "General", "conversationIds": []},
    {"id": "folder-research", "name": "Research", "conversationIds": []},
]


class UserSettingsService:
    @staticmethod
    async def get_or_create(db: AsyncSession, user_id: UUID) -> SQLAlchemyUserSettings:
        stmt = select(SQLAlchemyUserSettings).where(
            SQLAlchemyUserSettings.user_id == user_id
        )
        result = await db.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings is None:
            settings = SQLAlchemyUserSettings(
                user_id=user_id,
                folders=DEFAULT_FOLDERS,
                pinned_conversations=[],
                conversation_tags={},
                document_folders=[],
                document_folder_mappings={},
                document_custom_order=[],
                document_filter_presets=[],
                preferences={},
            )
            db.add(settings)
            await db.commit()
            await db.refresh(settings)

        return settings

    @staticmethod
    async def update(
        db: AsyncSession, user_id: UUID, patch: UserSettingsPatchSchema
    ) -> SQLAlchemyUserSettings:
        settings = await UserSettingsService.get_or_create(db, user_id)

        if patch.folders is not None:
            settings.folders = patch.folders
        if patch.pinned_conversations is not None:
            settings.pinned_conversations = patch.pinned_conversations
        if patch.conversation_tags is not None:
            settings.conversation_tags = patch.conversation_tags
        if patch.document_folders is not None:
            settings.document_folders = patch.document_folders
        if patch.document_folder_mappings is not None:
            settings.document_folder_mappings = patch.document_folder_mappings
        if patch.document_custom_order is not None:
            settings.document_custom_order = patch.document_custom_order
        if patch.document_filter_presets is not None:
            settings.document_filter_presets = patch.document_filter_presets
        if patch.preferences is not None:
            # Merge preferences dictionary
            updated_prefs = dict(settings.preferences or {})
            updated_prefs.update(patch.preferences)
            settings.preferences = updated_prefs

        await db.commit()
        await db.refresh(settings)
        return settings
