"""Admin-only user management endpoints."""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from fastapi import status as http_status

from app.models.schemas import (
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
    LLMDebugRequest,
    LLMDebugResponse,
)
from app.services.llm_service import llm_service
from app.services.user_service import user_service
from app.utils import gravatar_url

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_COOKIE_NAME = "senten_session"


def _require_admin(senten_session: str | None):
    """Validate session and require admin rights. Returns the admin User."""
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
    _, user = result
    if not user.is_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="ERR_ADMIN_REQUIRED",
        )
    return user


def _user_to_admin_response(user) -> AdminUserResponse:
    """Convert a User ORM object to AdminUserResponse including avatar_url."""
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        auth_provider=user.auth_provider,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        avatar_url=gravatar_url(user.email),
    )


@router.get("/admin/users", response_model=list[AdminUserResponse], tags=["Admin"])
async def list_users(senten_session: str = Cookie(default=None)):
    """List all users (admin only)."""
    _require_admin(senten_session)
    users = user_service.list_users()
    return [_user_to_admin_response(u) for u in users]


@router.post(
    "/admin/users",
    response_model=AdminUserResponse,
    status_code=http_status.HTTP_201_CREATED,
    tags=["Admin"],
)
async def create_user(
    body: AdminUserCreateRequest,
    senten_session: str = Cookie(default=None),
):
    """Create a new local user (admin only)."""
    _require_admin(senten_session)
    try:
        user = user_service.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
            is_admin=body.is_admin,
        )
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail="ERR_USER_EXISTS"
        )
    return _user_to_admin_response(user)


@router.put("/admin/users/{user_id}", response_model=AdminUserResponse, tags=["Admin"])
async def update_user(
    user_id: str,
    body: AdminUserUpdateRequest,
    senten_session: str = Cookie(default=None),
):
    """Update user attributes (is_active, is_admin, display_name). Admin only."""
    admin = _require_admin(senten_session)
    # Prevent admin from removing their own admin rights
    if user_id == admin.id and body.is_admin is False:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="ERR_CANNOT_REMOVE_OWN_ADMIN",
        )
    raw = body.model_dump()
    updates = {}
    for k, v in raw.items():
        if k == "email":
            # Always pass email (even None) so admin can clear it
            updates["email"] = v
        elif v is not None:
            updates[k] = v
    user = user_service.update_user(user_id, **updates)
    if not user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ERR_USER_NOT_FOUND",
        )
    return _user_to_admin_response(user)


@router.delete(
    "/admin/users/{user_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    tags=["Admin"],
)
async def delete_user(
    user_id: str,
    senten_session: str = Cookie(default=None),
):
    """Delete user and all associated data (admin only)."""
    admin = _require_admin(senten_session)
    if user_id == admin.id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="ERR_CANNOT_DELETE_SELF",
        )
    deleted = user_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ERR_USER_NOT_FOUND",
        )


@router.put("/admin/users/{user_id}/password", tags=["Admin"])
async def reset_password(
    user_id: str,
    body: AdminPasswordResetRequest,
    senten_session: str = Cookie(default=None),
):
    """Reset a user's password (admin only)."""
    _require_admin(senten_session)
    ok = user_service.set_password(user_id, body.new_password)
    if not ok:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="ERR_USER_NOT_FOUND",
        )
    return {"ok": True}


@router.post("/admin/debug/llm", response_model=LLMDebugResponse, tags=["Admin"])
async def debug_llm(
    body: LLMDebugRequest,
    senten_session: str = Cookie(default=None),
):
    """Debug-Endpunkt für LLM-Anfragen. Admin only.

    Gibt System-Prompt, User-Content, Raw-Response und verarbeitete Response zurück.
    Nie für produktive Übersetzungen verwenden — keine Usage-Aufzeichnung.
    """
    _require_admin(senten_session)

    if not llm_service.is_configured():
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERR_LLM_NOT_CONFIGURED",
        )

    try:
        result = await llm_service.debug_call(
            mode=body.mode,
            text=body.text,
            target_lang=body.target_lang,
            source_lang=body.source_lang,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("LLM debug call failed: %s", exc)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="ERR_LLM_CONNECTION",
        ) from exc

    return result
