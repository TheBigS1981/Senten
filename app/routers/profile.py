"""User profile and settings endpoints."""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from fastapi import status as http_status

from app.models.schemas import (
    ChangePasswordRequest,
    UserProfileResponse,
    UserSettingsResponse,
    UserSettingsSchema,
)
from app.services.user_service import user_service
from app.utils import gravatar_url

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_COOKIE_NAME = "senten_session"


def _require_session(senten_session: str | None) -> tuple:
    """Validate session cookie. Returns (session, user). Raises 401 if invalid."""
    if not senten_session:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="ERR_AUTH_REQUIRED",
        )
    result = user_service.get_session(senten_session)
    if not result:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="ERR_SESSION_INVALID",
        )
    return result


@router.get("/profile", response_model=UserProfileResponse, tags=["Profile"])
async def get_profile(senten_session: str = Cookie(default=None)):
    """Return current user profile including settings."""
    _, user = _require_session(senten_session)
    settings_obj = user_service.get_settings(user.id)
    if not settings_obj:
        raise HTTPException(status_code=500, detail="ERR_SESSION_NOT_FOUND")
    return UserProfileResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_provider=user.auth_provider,
        last_login_at=user.last_login_at,
        avatar_url=gravatar_url(user.email),
        settings=UserSettingsResponse.model_validate(settings_obj),
    )


@router.put("/profile/settings", response_model=UserSettingsResponse, tags=["Profile"])
async def update_settings(
    body: UserSettingsSchema,
    senten_session: str = Cookie(default=None),
):
    """Partial update of user settings. Only provided fields are changed."""
    _, user = _require_session(senten_session)
    updates = body.model_dump(exclude_none=True)
    # Empty string for accent_color means reset to null
    if "accent_color" in updates and updates["accent_color"] == "":
        updates["accent_color"] = None
    result = user_service.update_settings(user.id, **updates)
    if not result:
        raise HTTPException(
            status_code=500,
            detail="ERR_SETTINGS_SAVE_FAILED",
        )
    return UserSettingsResponse.model_validate(result)


@router.put("/profile/password", tags=["Profile"])
async def change_password(
    body: ChangePasswordRequest,
    senten_session: str = Cookie(default=None),
):
    """Change own password (local auth users only)."""
    _, user = _require_session(senten_session)
    if user.auth_provider != "local" or not user.password_hash:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="ERR_PASSWORD_LOCAL_ONLY",
        )
    if not user_service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="ERR_PASSWORD_WRONG",
        )
    user_service.set_password(user.id, body.new_password)
    return {"ok": True}
