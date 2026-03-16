"""Shared utility helpers used across routers."""

import hashlib
from typing import Optional

from fastapi import Request


def get_user_id(request: Request) -> str:
    """Extract the authenticated user ID from the request state.

    Falls back to ``"anonymous"`` when no authentication is configured or
    the auth middleware placed no user on the state.
    """
    return getattr(request.state, "user_id", "anonymous")


def gravatar_url(email: Optional[str], size: int = 40) -> str:
    """Generate Gravatar URL for given email. Falls back to identicon if no email."""
    if not email:
        return f"https://www.gravatar.com/avatar/?d=identicon&s={size}"
    digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=identicon"
