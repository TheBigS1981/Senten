"""Authentication middleware.

Supports four authentication modes (evaluated in this order):

1. **Session Cookie** — always checked first: if a valid ``senten_session``
   HttpOnly cookie is present, the user is loaded from the session store.

2. **OIDC / JWT** — when ``OIDC_DISCOVERY_URL`` is set in the environment.
   Bearer tokens are validated against the OIDC provider's JWKS endpoint.
   JWKS keys are cached and refreshed every hour.
   OIDC users are auto-provisioned in the ``users`` table on first login.

3. **HTTP Basic Auth** — fallback when ``AUTH_USERNAME`` and
   ``AUTH_PASSWORD`` are set but OIDC is not configured.

4. **Anonymous** — no auth configured; every request is allowed through
   with ``request.state.user_id = "anonymous"`` and ``request.state.user = None``.
   If ``ALLOW_ANONYMOUS=false``, unauthenticated browser requests are redirected
   to ``/login``; API requests receive HTTP 401.

Exempt paths (never authenticated):
  - ``/health``
  - ``/static/`` (static file subtree)
  - ``/favicon``
  - ``/login`` (login page itself)
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import httpx
import jwt as pyjwt
from jwt import PyJWKClient, PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter for auth endpoints: 5 requests per minute per IP
#
# NOTE: _auth_rate_store is in-process memory. In a multi-worker deployment
# (multiple uvicorn workers or gunicorn), each worker maintains its own store,
# so the effective limit is max_requests × num_workers per IP.
# For the current single-worker Docker deployment this is acceptable.
# For multi-worker deployments, replace with a shared store (e.g. Redis).
_AUTH_RATE_LIMIT = {"max_requests": 5, "window_seconds": 60}
_auth_rate_store: dict[str, list[float]] = defaultdict(list)

# Paths that bypass authentication entirely
_EXEMPT_PREFIXES = (
    "/health",
    "/static/",
    "/favicon",
    "/login",
    "/api/auth/login",
    "/api/auth/logout",
)

# JWKS cache TTL in seconds (1 hour)
_JWKS_TTL = 3600

# Retry configuration for JWKS fetch
_JWKS_MAX_RETRIES = 3
_JWKS_INITIAL_DELAY = 0.5  # seconds

_SESSION_COOKIE_NAME = "senten_session"


class AuthMiddleware(BaseHTTPMiddleware):
    """Unified auth middleware: Session Cookie → OIDC → Basic → Anonymous."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._oidc_mode: bool = bool(settings.oidc_discovery_url)
        self._basic_mode: bool = bool(
            not self._oidc_mode and settings.auth_username and settings.auth_password
        )
        # JWKS client — lazily initialised on first OIDC request, then reused.
        # PyJWKClient caches keys internally; we also cache the JWKS URI.
        self._jwks_client: Optional[PyJWKClient] = None
        self._jwks_uri: Optional[str] = None
        # Counter for periodic eviction of stale rate-limit entries (see _check_auth_rate_limit)
        self._rate_check_count: int = 0

        if self._oidc_mode:
            logger.info("Auth: OIDC-Modus aktiv (%s)", settings.oidc_discovery_url)
        elif self._basic_mode:
            logger.info("Auth: HTTP-Basic-Auth-Modus aktiv")
        else:
            logger.info("Auth: Kein Auth konfiguriert — anonymer Zugriff")

    # ------------------------------------------------------------------
    # Middleware dispatch
    # ------------------------------------------------------------------

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request, handling proxies.

        Only trusts X-Forwarded-For header if the request comes from a trusted proxy.
        """
        # Only trust X-Forwarded-For from trusted proxies to prevent IP spoofing
        client_host = request.client.host if request.client else ""
        if client_host in settings.trusted_proxies:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return client_host if client_host else "unknown"

    def _check_auth_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """Check if client has exceeded auth rate limit. Returns (allowed, retry_after).

        Performs periodic housekeeping every 500 calls: IP entries whose last
        request was more than 2× the rate-limit window ago are evicted to
        prevent unbounded memory growth under sustained scanning.
        """
        now = time.time()
        window = _AUTH_RATE_LIMIT["window_seconds"]
        max_requests = _AUTH_RATE_LIMIT["max_requests"]

        # Periodic housekeeping — evict stale IP entries
        self._rate_check_count += 1
        if self._rate_check_count >= 500:
            self._rate_check_count = 0
            stale_cutoff = now - window * 2
            stale_ips = [
                ip
                for ip, timestamps in list(_auth_rate_store.items())
                if timestamps and max(timestamps) < stale_cutoff
            ]
            for ip in stale_ips:
                del _auth_rate_store[ip]
            if stale_ips:
                logger.debug(
                    "Auth rate store: evicted %d stale entries", len(stale_ips)
                )

        # Clean old timestamps for this IP
        timestamps = _auth_rate_store[client_ip]
        timestamps = [ts for ts in timestamps if now - ts < window]
        _auth_rate_store[client_ip] = timestamps

        if len(timestamps) >= max_requests:
            # Calculate retry_after based on oldest request in window
            oldest = min(timestamps)
            retry_after = int(window - (now - oldest)) + 1
            return False, retry_after

        # Add current request
        timestamps.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            request.state.user_id = "anonymous"
            request.state.user = None
            return await call_next(request)

        # --- Session cookie check (runs for all auth modes) ---
        session_cookie = request.cookies.get(_SESSION_COOKIE_NAME)
        if session_cookie:
            result = await self._validate_session_cookie(session_cookie)
            if result:
                _session, user = result
                request.state.user_id = user.id
                request.state.user = user
                return await call_next(request)
            # Invalid/expired cookie — proceed to fallback auth, clear cookie in response
            response = await self._handle_fallback_auth(request, call_next)
            response.delete_cookie(_SESSION_COOKIE_NAME, path="/")
            return response

        return await self._handle_fallback_auth(request, call_next)

    async def _handle_fallback_auth(self, request: Request, call_next) -> Response:
        """Handle auth when no valid session cookie is present."""
        # Apply rate limiting to explicit auth modes
        if self._oidc_mode or self._basic_mode:
            client_ip = self._get_client_ip(request)
            allowed, retry_after = self._check_auth_rate_limit(client_ip)
            if not allowed:
                logger.warning("Rate limit exceeded for auth from IP: %s", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Zu viele Authentifizierungsversuche. Bitte warte einen Moment.",
                        "retry_after": retry_after,
                    },
                )

        if self._oidc_mode:
            return await self._handle_oidc(request, call_next)
        if self._basic_mode:
            return await self._handle_basic_auth(request, call_next)

        # Anonymous mode
        if not settings.allow_anonymous:
            accept = request.headers.get("Accept", "")
            if "text/html" in accept and not request.url.path.startswith("/api"):
                from starlette.responses import RedirectResponse

                return RedirectResponse(url="/login")
            return JSONResponse(
                status_code=401,
                content={"detail": "Anmeldung erforderlich."},
            )

        request.state.user_id = "anonymous"
        request.state.user = None
        return await call_next(request)

    # ------------------------------------------------------------------
    # Session cookie validation
    # ------------------------------------------------------------------

    async def _validate_session_cookie(self, session_id: str) -> Optional[tuple]:
        """Validate session cookie. Returns (session, user) or None if invalid."""
        try:
            from app.services.user_service import user_service

            result = user_service.get_session(session_id)
            return result
        except Exception as exc:
            logger.warning("Session validation error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # OIDC / JWT
    # ------------------------------------------------------------------

    async def _handle_oidc(self, request: Request, call_next) -> Response:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer-Token erforderlich."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]
        payload = await self._validate_jwt(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Ungültiger oder abgelaufener Token."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        subject = payload.get("sub", "oidc-user")
        # Auto-provision OIDC user on first login
        try:
            from app.services.user_service import user_service

            preferred_username = (
                payload.get("preferred_username") or payload.get("email") or subject
            )
            user = user_service.provision_oidc_user(
                subject=subject, username=preferred_username
            )
            request.state.user_id = user.id
            request.state.user = user
        except Exception as exc:
            logger.warning("OIDC auto-provisioning failed: %s", exc)
            request.state.user_id = subject
            request.state.user = None

        return await call_next(request)

    async def _fetch_jwks_uri(self) -> Optional[str]:
        """Fetch JWKS URI from the OIDC discovery endpoint with retry and domain validation."""
        last_exception: Optional[Exception] = None
        for attempt in range(_JWKS_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    discovery_resp = await client.get(settings.oidc_discovery_url)
                    discovery_resp.raise_for_status()
                    jwks_uri = discovery_resp.json().get("jwks_uri")
                    if not jwks_uri:
                        logger.error("OIDC Discovery enthält keinen jwks_uri")
                        return None

                    # Validate jwks_uri is from trusted domain (SEC-013)
                    parsed_jwks_uri = urlparse(jwks_uri)
                    trusted_domain = urlparse(settings.oidc_discovery_url).netloc
                    if parsed_jwks_uri.netloc != trusted_domain:
                        logger.error(
                            "JWKS URI domain not allowed: %s (expected: %s)",
                            parsed_jwks_uri.netloc,
                            trusted_domain,
                        )
                        return None

                    return jwks_uri
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "OIDC Discovery fehlgeschlagen (Versuch %d/%d): %s",
                    attempt + 1,
                    _JWKS_MAX_RETRIES,
                    exc,
                )
                if attempt < _JWKS_MAX_RETRIES - 1:
                    delay = _JWKS_INITIAL_DELAY * (2**attempt)
                    await asyncio.sleep(delay)

        logger.error(
            "OIDC Discovery nach %d Versuchen fehlgeschlagen: %s",
            _JWKS_MAX_RETRIES,
            last_exception,
        )
        return None

    async def _validate_jwt(self, token: str) -> Optional[dict]:
        """Validate a JWT Bearer token using PyJWT and the OIDC provider's JWKS.

        Uses cached JWKS client to avoid fetching the JWKS on every request.
        The PyJWKClient internally caches signing keys by kid.
        """
        # Lazily fetch JWKS URI and create client once
        if self._jwks_uri is None:
            self._jwks_uri = await self._fetch_jwks_uri()
        if not self._jwks_uri:
            return None

        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self._jwks_uri, cache_keys=True)

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        except Exception as exc:
            logger.warning("JWKS-Schlüssel konnte nicht abgerufen werden: %s", exc)
            return None

        try:
            # Accept common asymmetric algorithms used by OIDC providers.
            # HS256 (symmetric) is intentionally excluded — it would require sharing a secret.
            payload = pyjwt.decode(
                token,
                key=signing_key.key,
                algorithms=[
                    "RS256",
                    "RS384",
                    "RS512",
                    "ES256",
                    "ES384",
                    "ES512",
                    "PS256",
                ],
                audience=settings.oidc_client_id,
            )
            return payload
        except PyJWTError as exc:
            logger.warning("JWT-Validierung fehlgeschlagen: %s", exc)
            return None

    # ------------------------------------------------------------------
    # HTTP Basic Auth
    # ------------------------------------------------------------------

    async def _handle_basic_auth(self, request: Request, call_next) -> Response:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return self._basic_challenge()

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return self._basic_challenge()

        expected_user = settings.auth_username or ""
        expected_pass = (
            settings.auth_password.get_secret_value() if settings.auth_password else ""
        )

        # Constant-time comparison to prevent timing attacks
        user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
        pass_ok = hmac.compare_digest(
            hashlib.sha256(password.encode()).digest(),
            hashlib.sha256(expected_pass.encode()).digest(),
        )

        if not (user_ok and pass_ok):
            return self._basic_challenge()

        request.state.user_id = username
        request.state.user = None  # Basic auth has no User DB object
        return await call_next(request)

    @staticmethod
    def _basic_challenge() -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentifizierung erforderlich."},
            headers={"WWW-Authenticate": 'Basic realm="Senten"'},
        )
