"""Authentication endpoints: Login and Logout."""

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi import status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.models.schemas import LoginRequest
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiter for login endpoint - uses IP-based key
# Disable via DISABLE_RATE_LIMIT env var (for testing)
_login_limit = (
    "5/minute" if os.environ.get("DISABLE_RATE_LIMIT") != "1" else "1000/minute"
)
login_limiter = Limiter(key_func=get_remote_address)

_SESSION_COOKIE_NAME = "senten_session"

# Dummy hash used during constant-time comparison when user is not found.
# Prevents username enumeration via timing attacks.
_DUMMY_HASH = "$2b$12$invalidhashfortimingiprotectiononly1234567890abcdefghij"


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request, handling proxies.

    Only trusts X-Forwarded-For header if the request comes from a trusted proxy.
    """
    client_host = request.client.host if request.client else ""
    if client_host in settings.trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_host if client_host else "unknown"


@router.post("/auth/login", tags=["Auth"])
@login_limiter.limit(_login_limit)
async def login(body: LoginRequest, request: Request, response: Response):
    """Authenticate with username + password, set HttpOnly session cookie."""
    user = user_service.get_user_by_username(body.username)

    # Always run bcrypt verify to prevent timing-based username enumeration
    candidate_hash = (
        user.password_hash if (user and user.password_hash) else _DUMMY_HASH
    )
    password_ok = user_service.verify_password(body.password, candidate_hash)

    if not user or not password_ok or not user.is_active:
        logger.warning("Failed login attempt for username: %s", body.username)
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="ERR_AUTH_REQUIRED",
        )

    session = user_service.create_session(
        user_id=user.id,
        remember_me=body.remember_me,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    user_service.update_last_login(user.id)

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())

    response.set_cookie(
        key=_SESSION_COOKIE_NAME,
        value=session.id,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    logger.info("User logged in: %s", user.username)
    return {"ok": True, "username": user.username, "is_admin": user.is_admin}


@router.post("/auth/logout", tags=["Auth"])
async def logout(
    response: Response,
    senten_session: str = Cookie(default=None),
):
    """Invalidate session and delete session cookie."""
    if senten_session:
        user_service.delete_session(senten_session)
    response.delete_cookie(key=_SESSION_COOKIE_NAME, path="/")
    return {"ok": True}
