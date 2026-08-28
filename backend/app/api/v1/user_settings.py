from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user_context, get_db
from app.auth.domain.schemas import (
    UserSettingsPatchSchema,
    UserSettingsResponseSchema,
)
from app.auth.services.user_settings_service import UserSettingsService

router = APIRouter(prefix="/user/settings", tags=["User Settings"])


@router.get(
    "",
    response_model=UserSettingsResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def get_user_settings(
    user_context: dict[str, Any] = Depends(get_current_user_context),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve workspace organization data, folders, tags, pins, and preferences
    for the authenticated user.
    """
    user_id = UUID(user_context["user_id"])
    settings = await UserSettingsService.get_or_create(db, user_id)
    return settings


@router.patch(
    "",
    response_model=UserSettingsResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def update_user_settings(
    patch: UserSettingsPatchSchema,
    user_context: dict[str, Any] = Depends(get_current_user_context),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Partially update workspace folders, pinned conversations, tags, document library
    organization, or preferences for the authenticated user.
    """
    user_id = UUID(user_context["user_id"])
    settings = await UserSettingsService.update(db, user_id, patch)
    return settings
