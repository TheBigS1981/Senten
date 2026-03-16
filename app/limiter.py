"""Shared rate limiter configuration.

This module provides a centralized rate limiter instance with a hybrid
key function that uses user_id for authenticated users and IP address
for anonymous users.

The rate limit can be configured via environment variables:
- RATE_LIMIT_TRANSLATE: rate for translation endpoints (default: "30/minute")
- RATE_LIMIT_AUTH: rate for auth endpoints (default: "5/minute")
- DISABLE_RATE_LIMIT: if set to "1", rate limiting is disabled entirely (for tests)
"""

import logging
import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """Hybrid rate limit key: uses user_id for authenticated users, IP for anonymous."""
    user_id = getattr(request.state, "user_id", None)
    if user_id and user_id != "anonymous":
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def _get_rate_limit(default: str) -> str:
    """Get rate limit from environment or return default."""
    if os.environ.get("DISABLE_RATE_LIMIT") == "1":
        logger.warning(
            "DISABLE_RATE_LIMIT=1 — all rate limiting is disabled. Never use in production."
        )
        return "1000/minute"  # Effectively unlimited for tests
    return os.environ.get("RATE_LIMIT_TRANSLATE", default)


# Rate limiter instance - uses user_id for authenticated, IP for anonymous
limiter = Limiter(key_func=get_rate_limit_key)
limiter.default_limits = [_get_rate_limit("30/minute")]
