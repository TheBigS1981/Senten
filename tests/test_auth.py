"""Unit tests for the AuthMiddleware.

Tests the three authentication modes (OIDC, Basic, Anonymous) and the
auth bypass for exempt paths like /health and /static.

Note: Tests are designed to work around the fact that middleware is instantiated
at app startup. We test the middleware's dispatch method directly or use
settings patching.
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.auth import _AUTH_RATE_LIMIT, AuthMiddleware, _auth_rate_store


class RequestBuilder:
    """Helper to build mock requests for testing middleware."""

    @staticmethod
    def create_mock_request(path: str, headers: dict | None = None):
        """Create a mock request with the given path and headers."""
        request = MagicMock(spec=Request)
        request.url.path = path

        # Create a proper headers dict-like object
        headers_dict = headers or {}
        request.headers = type(
            "Headers",
            (),
            {"get": lambda self, key, default=None: headers_dict.get(key, default)},
        )()

        request.state = MagicMock()

        # Mock URL
        mock_url = MagicMock()
        mock_url.path = path
        request.url = mock_url

        return request


class TestAuthModesDetection:
    """Test that middleware correctly detects auth mode from settings."""

    def test_anonymous_mode_when_no_auth_configured(self):
        """Middleware should be in anonymous mode when no auth is configured."""
        middleware = AuthMiddleware(MagicMock())

        # Should be anonymous mode (no OIDC, no Basic)
        assert middleware._oidc_mode is False
        assert middleware._basic_mode is False

    def test_basic_mode_when_username_and_password_set(self):
        """Middleware should be in Basic mode when credentials are configured."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "testuser"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "testpass"

            middleware = AuthMiddleware(MagicMock())

            assert middleware._oidc_mode is False
            assert middleware._basic_mode is True

    def test_oidc_mode_when_discovery_url_set(self):
        """Middleware should be in OIDC mode when OIDC is configured."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            assert middleware._oidc_mode is True
            assert middleware._basic_mode is False


class TestBasicAuthMode:
    """Tests for HTTP Basic Authentication mode."""

    @pytest.fixture
    def middleware_with_basic_auth(self):
        """Create middleware in Basic Auth mode."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "testuser"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "testpass123"

            middleware = AuthMiddleware(MagicMock())

            # Keep the patch active by yielding the middleware along with the patcher
            yield middleware, mock_settings

    @pytest.mark.asyncio
    async def test_valid_credentials_grant_access(self, middleware_with_basic_auth):
        """Valid Basic Auth credentials should set user_id to the username."""
        middleware, mock_settings = middleware_with_basic_auth

        password = "testpass123"
        auth_header = (
            f"Basic {base64.b64encode(f'testuser:{password}'.encode()).decode()}"
        )

        request = RequestBuilder.create_mock_request(
            "/protected", {"Authorization": auth_header}
        )

        user_id_holder = {}

        async def mock_call_next(req):
            user_id_holder["user_id"] = req.state.user_id
            return JSONResponse({"user_id": req.state.user_id})

        response = await middleware.dispatch(request, mock_call_next)

        # Response should be successful (call_next was called)
        assert response.status_code == 200
        assert user_id_holder["user_id"] == "testuser"

    @pytest.mark.asyncio
    async def test_invalid_credentials_return_401(self, middleware_with_basic_auth):
        """Invalid Basic Auth credentials should return 401."""
        middleware, mock_settings = middleware_with_basic_auth

        # Use wrong password
        request = RequestBuilder.create_mock_request(
            "/protected",
            {
                "Authorization": f"Basic {base64.b64encode(b'testuser:wrongpass').decode()}"
            },
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_credentials_return_401(self, middleware_with_basic_auth):
        """Missing Authorization header should return 401."""
        middleware, mock_settings = middleware_with_basic_auth

        request = RequestBuilder.create_mock_request("/protected", {})

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_returns_401(self, middleware_with_basic_auth):
        """Malformed Authorization header should return 401."""
        middleware, mock_settings = middleware_with_basic_auth

        request = RequestBuilder.create_mock_request(
            "/protected", {"Authorization": "NotBasic at all"}
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401


class TestOIDCAuthMode:
    """Tests for OIDC/JWT authentication mode."""

    @pytest.fixture
    def middleware_with_oidc(self):
        """Create middleware in OIDC mode."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = (
                "https://idp.example.com/.well-known/openid-configuration"
            )
            mock_settings.oidc_client_id = "test-client-id"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            yield middleware, mock_settings

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, middleware_with_oidc):
        """Missing Bearer token should return 401."""
        middleware, mock_settings = middleware_with_oidc

        request = RequestBuilder.create_mock_request("/protected", {})

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_format_returns_401(self, middleware_with_oidc):
        """Non-Bearer token format should return 401."""
        middleware, mock_settings = middleware_with_oidc

        request = RequestBuilder.create_mock_request(
            "/protected", {"Authorization": "Bearer"}
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_returns_401(self, middleware_with_oidc):
        """When JWKS fetch fails, should return 401."""
        middleware, mock_settings = middleware_with_oidc

        # Mock _fetch_jwks to return None (fetch failure)
        middleware._fetch_jwks = AsyncMock(return_value=None)

        request = RequestBuilder.create_mock_request(
            "/protected", {"Authorization": "Bearer some-token"}
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401


class TestAnonymousMode:
    """Tests for anonymous mode (no auth configured)."""

    @pytest.fixture
    def middleware_anonymous(self):
        """Create middleware in anonymous mode."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())
            yield middleware

    @pytest.mark.asyncio
    async def test_anonymous_allows_access(self, middleware_anonymous):
        """Anonymous mode should allow all requests."""
        request = RequestBuilder.create_mock_request("/protected", {})

        async def mock_call_next(req):
            return JSONResponse({"user_id": req.state.user_id})

        response = await middleware_anonymous.dispatch(request, mock_call_next)

        # Response should be successful (call_next was called)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_anonymous_sets_user_id(self, middleware_anonymous):
        """Anonymous mode should set user_id to 'anonymous'."""
        request = RequestBuilder.create_mock_request("/protected", {})
        user_id_holder = {}

        async def mock_call_next(req):
            user_id_holder["user_id"] = req.state.user_id
            return JSONResponse({})

        await middleware_anonymous.dispatch(request, mock_call_next)

        assert user_id_holder["user_id"] == "anonymous"


class TestExemptPathHandling:
    """Test that exempt paths set user_id to anonymous."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/health",
            "/static/file.txt",
            "/favicon.ico",
        ],
    )
    async def test_exempt_paths_set_anonymous(self, path):
        """Exempt paths should set user_id to 'anonymous' and bypass auth."""
        middleware = AuthMiddleware(MagicMock())

        request = RequestBuilder.create_mock_request(path, {})
        user_id_holder = {}

        async def mock_call_next(req):
            user_id_holder["user_id"] = req.state.user_id
            return JSONResponse({})

        await middleware.dispatch(request, mock_call_next)

        assert user_id_holder["user_id"] == "anonymous"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/login",
            "/api/auth/logout",
            "/login",
        ],
    )
    async def test_auth_endpoints_exempt_when_allow_anonymous_false(self, path):
        """Login/logout endpoints must be reachable even when allow_anonymous=False.

        Regression test: POST /api/auth/login was blocked by the middleware before
        reaching the FastAPI router, causing 'Anmeldung erforderlich.' on every
        login attempt — regardless of credentials.
        """
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = None
            mock_settings.auth_password = None
            mock_settings.allow_anonymous = False

            middleware = AuthMiddleware(MagicMock())

        request = RequestBuilder.create_mock_request(path, {})
        reached_handler = {}

        async def mock_call_next(req):
            reached_handler["called"] = True
            return JSONResponse({"ok": True})

        await middleware.dispatch(request, mock_call_next)

        assert reached_handler.get("called") is True, (
            f"Path {path!r} was blocked by AuthMiddleware — "
            "login/logout must be exempt from auth checks"
        )


class TestConstantTimeComparison:
    """Verify that Basic Auth uses constant-time comparison."""

    @pytest.mark.asyncio
    async def test_wrong_password_always_returns_401(self):
        """Constant-time comparison must reject all wrong passwords — no early exit."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "user"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "correct"
            middleware = AuthMiddleware(MagicMock())

        async def mock_call_next(req):
            return JSONResponse({})

        # Try various wrong passwords including empty string and similar-looking ones
        for wrong_pw in ["", "correc", "correct1", "CORRECT"]:
            auth = f"Basic {base64.b64encode(f'user:{wrong_pw}'.encode()).decode()}"
            request = RequestBuilder.create_mock_request(
                "/protected", {"Authorization": auth}
            )
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 401, (
                f"Password '{wrong_pw}' should be rejected"
            )


# ---------------------------------------------------------------------------
# New tests to close coverage gaps
# ---------------------------------------------------------------------------


class TestGetClientIp:
    """Tests for _get_client_ip — X-Forwarded-For header parsing and fallback behavior."""

    def test_get_client_ip_uses_x_forwarded_for_first_entry(self):
        """Should return the first IP from X-Forwarded-For when client is trusted proxy."""
        middleware = AuthMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1, 172.16.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"  # Trusted proxy

        ip = middleware._get_client_ip(request)

        assert ip == "10.0.0.1"

    def test_get_client_ip_strips_whitespace_from_forwarded_for(self):
        """Leading/trailing whitespace around the first IP must be stripped."""
        middleware = AuthMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "  203.0.113.5  , 10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"  # Trusted proxy

        ip = middleware._get_client_ip(request)

        assert ip == "203.0.113.5"

    def test_get_client_ip_x_forwarded_for_ignored_from_untrusted(self):
        """X-Forwarded-For should be ignored when client is not a trusted proxy."""
        middleware = AuthMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        request.client = MagicMock()
        request.client.host = "203.0.113.50"  # Not a trusted proxy

        ip = middleware._get_client_ip(request)

        assert ip == "203.0.113.50"  # Should return client.host, not X-Forwarded-For

    def test_get_client_ip_falls_back_to_client_host(self):
        """Without X-Forwarded-For, should fall back to request.client.host."""
        middleware = AuthMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        ip = middleware._get_client_ip(request)

        assert ip == "127.0.0.1"

    def test_get_client_ip_returns_unknown_when_no_client(self):
        """When request.client is None and no X-Forwarded-For, return 'unknown'."""
        middleware = AuthMiddleware(MagicMock())

        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "unknown"


class TestRateLimitHousekeeping:
    """Tests for _check_auth_rate_limit — stale-entry eviction and rate-exceeded behavior."""

    TEST_IPS = ["192.0.2.99", "192.0.2.50", "10.0.0.200", "10.0.0.201"]

    def setup_method(self):
        """Remove all test IPs from the shared rate store before each test."""
        for ip in self.TEST_IPS:
            _auth_rate_store.pop(ip, None)

    def teardown_method(self):
        """Remove all test IPs from the shared rate store after each test."""
        for ip in self.TEST_IPS:
            _auth_rate_store.pop(ip, None)

    def test_rate_limit_evicts_stale_entries_at_500_calls(self):
        """After 500 calls, stale IP entries older than 2× window should be evicted."""
        import time

        middleware = AuthMiddleware(MagicMock())
        middleware._rate_check_count = 499  # next call triggers housekeeping

        # Plant a stale entry: last request was 3× the window ago
        stale_ip = "192.0.2.99"
        window = _AUTH_RATE_LIMIT["window_seconds"]
        _auth_rate_store[stale_ip] = [time.time() - window * 3]

        # This call should trigger housekeeping and evict the stale entry
        middleware._check_auth_rate_limit("10.0.0.1")

        assert stale_ip not in _auth_rate_store
        assert middleware._rate_check_count == 0  # reset after housekeeping

    def test_rate_limit_does_not_evict_active_entries(self):
        """Active IP entries (recent requests) must NOT be evicted during housekeeping."""
        import time

        middleware = AuthMiddleware(MagicMock())
        middleware._rate_check_count = 499

        active_ip = "192.0.2.50"
        _auth_rate_store[active_ip] = [
            time.time() - 10
        ]  # 10 seconds ago — still active

        middleware._check_auth_rate_limit("10.0.0.1")

        assert active_ip in _auth_rate_store

    def test_rate_limit_exceeded_returns_false_with_retry_after(self):
        """When max_requests is exceeded, should return (False, retry_after > 0)."""
        import time

        middleware = AuthMiddleware(MagicMock())

        # Fill the rate store with max_requests timestamps within the window
        client_ip = "10.0.0.200"
        now = time.time()
        _auth_rate_store[client_ip] = [now - 5] * _AUTH_RATE_LIMIT["max_requests"]

        allowed, retry_after = middleware._check_auth_rate_limit(client_ip)

        assert allowed is False
        assert retry_after > 0

    def test_rate_limit_allowed_when_under_limit(self):
        """When under the request limit, should return (True, 0)."""
        middleware = AuthMiddleware(MagicMock())

        client_ip = "10.0.0.201"
        _auth_rate_store[client_ip] = []  # no prior requests

        allowed, retry_after = middleware._check_auth_rate_limit(client_ip)

        assert allowed is True
        assert retry_after == 0


class TestRateLimitDispatch:
    """Tests for rate-limit 429 response in dispatch() — both Basic and OIDC modes."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429_in_basic_mode(self):
        """When rate limit is exceeded in Basic Auth mode, dispatch must return 429."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "user"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "pass"

            middleware = AuthMiddleware(MagicMock())

            # Patch _check_auth_rate_limit to simulate exceeded limit — patch active during dispatch
            with patch.object(
                middleware, "_check_auth_rate_limit", return_value=(False, 42)
            ):
                request = RequestBuilder.create_mock_request("/protected", {})

                async def mock_call_next(req):
                    return JSONResponse({"error": "should not reach here"})

                response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 429
        body = response.body
        data = json.loads(bytes(body))
        assert "retry_after" in data
        assert data["retry_after"] == 42

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429_in_oidc_mode(self):
        """When rate limit is exceeded in OIDC mode, dispatch must return 429."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            with patch.object(
                middleware, "_check_auth_rate_limit", return_value=(False, 30)
            ):
                request = RequestBuilder.create_mock_request("/protected", {})

                async def mock_call_next(req):
                    return JSONResponse({"error": "should not reach here"})

                response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 429


class TestOIDCUserIdSet:
    """Tests for OIDC user_id assignment — OIDC auto-provisioning sets user_id from DB."""

    @pytest.mark.asyncio
    async def test_valid_jwt_sets_user_id_from_provisioned_user(self):
        """A valid JWT with a 'sub' claim must provision a DB user and set user_id to user.id."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        provisioned_user = MagicMock()
        provisioned_user.id = "db-uuid-for-user-123"

        # Patch _validate_jwt + provision_oidc_user so no real DB is needed.
        # Use patch.object on the imported singleton to avoid module-resolution
        # issues on Python 3.11 where app.services.user_service may not yet be
        # an attribute of the app.services package namespace.
        from app.services.user_service import user_service as _user_service

        with (
            patch.object(
                middleware,
                "_validate_jwt",
                new_callable=AsyncMock,
                return_value={"sub": "user-123", "email": "user@example.com"},
            ),
            patch.object(
                _user_service,
                "provision_oidc_user",
                return_value=provisioned_user,
            ),
        ):
            request = RequestBuilder.create_mock_request(
                "/protected", {"Authorization": "Bearer valid.token.here"}
            )
            user_id_holder = {}

            async def mock_call_next(req):
                user_id_holder["user_id"] = req.state.user_id
                return JSONResponse({})

            await middleware.dispatch(request, mock_call_next)

        assert user_id_holder["user_id"] == "db-uuid-for-user-123"

    @pytest.mark.asyncio
    async def test_valid_jwt_without_sub_provisions_with_default_subject(self):
        """A valid JWT without a 'sub' claim must provision with subject 'oidc-user'."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        provisioned_user = MagicMock()
        provisioned_user.id = "db-uuid-for-oidc-user"

        from app.services.user_service import user_service as _user_service

        with (
            patch.object(
                middleware,
                "_validate_jwt",
                new_callable=AsyncMock,
                return_value={"email": "user@example.com"},  # no 'sub'
            ),
            patch.object(
                _user_service,
                "provision_oidc_user",
                return_value=provisioned_user,
            ),
        ):
            request = RequestBuilder.create_mock_request(
                "/protected", {"Authorization": "Bearer valid.token.here"}
            )
            user_id_holder = {}

            async def mock_call_next(req):
                user_id_holder["user_id"] = req.state.user_id
                return JSONResponse({})

            await middleware.dispatch(request, mock_call_next)

        assert user_id_holder["user_id"] == "db-uuid-for-oidc-user"


class TestFetchJwksUri:
    """Tests for _fetch_jwks_uri() — OIDC discovery document fetching, domain validation, and retry behavior."""

    @pytest.mark.asyncio
    async def test_fetch_jwks_uri_success(self):
        """Should return the jwks_uri from a successful discovery response."""
        discovery_payload = {
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
            "issuer": "https://idp.example.com",
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = discovery_payload

        with (
            patch("app.middleware.auth.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.oidc_discovery_url = (
                "https://idp.example.com/.well-known/openid-configuration"
            )
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_http_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await middleware._fetch_jwks_uri()

        assert result == "https://idp.example.com/.well-known/jwks.json"

    @pytest.mark.asyncio
    async def test_fetch_jwks_uri_missing_jwks_uri_returns_none(self):
        """When the discovery document has no 'jwks_uri', should return None."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "issuer": "https://idp.example.com"
        }  # no jwks_uri

        with (
            patch("app.middleware.auth.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.oidc_discovery_url = (
                "https://idp.example.com/.well-known/openid-configuration"
            )
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_http_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await middleware._fetch_jwks_uri()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_jwks_uri_untrusted_domain_returns_none(self):
        """When jwks_uri points to a different domain, should return None (SEC-013)."""
        # jwks_uri is on a different domain — should be rejected
        discovery_payload = {
            "jwks_uri": "https://evil.attacker.com/.well-known/jwks.json",
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = discovery_payload

        with (
            patch("app.middleware.auth.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.oidc_discovery_url = (
                "https://idp.example.com/.well-known/openid-configuration"
            )
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_http_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await middleware._fetch_jwks_uri()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_jwks_uri_http_error_retries_and_returns_none(self):
        """HTTP errors during discovery should trigger retries and ultimately return None."""
        with (
            patch("app.middleware.auth.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new_callable=AsyncMock),  # skip actual delays
        ):
            mock_settings.oidc_discovery_url = (
                "https://idp.example.com/.well-known/openid-configuration"
            )
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_http_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await middleware._fetch_jwks_uri()

        assert result is None


class TestValidateJwt:
    """Tests for _validate_jwt() — JWT signature verification and error handling."""

    @pytest.mark.asyncio
    async def test_validate_jwt_returns_none_when_jwks_uri_fetch_fails(self):
        """When _fetch_jwks_uri returns None, _validate_jwt must return None."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        with patch.object(
            middleware, "_fetch_jwks_uri", new_callable=AsyncMock, return_value=None
        ):
            result = await middleware._validate_jwt("some.jwt.token")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_returns_none_when_signing_key_fetch_fails(self):
        """When get_signing_key_from_jwt raises, _validate_jwt must return None."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        # Pre-set jwks_uri so _fetch_jwks_uri is not called
        middleware._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.side_effect = Exception(
            "key not found"
        )
        middleware._jwks_client = mock_jwks_client

        result = await middleware._validate_jwt("some.jwt.token")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_returns_none_on_pyjwt_error(self):
        """When pyjwt.decode raises PyJWTError, _validate_jwt must return None."""
        import jwt as pyjwt
        from jwt import PyJWTError

        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        middleware._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
        middleware._jwks_client = mock_jwks_client

        with patch(
            "app.middleware.auth.pyjwt.decode",
            side_effect=PyJWTError("invalid signature"),
        ):
            result = await middleware._validate_jwt("some.jwt.token")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_success_returns_payload(self):
        """When pyjwt.decode succeeds, _validate_jwt must return the decoded payload."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        middleware._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
        middleware._jwks_client = mock_jwks_client

        expected_payload = {
            "sub": "user-456",
            "email": "user@example.com",
            "aud": "test-client",
        }

        with patch("app.middleware.auth.pyjwt.decode", return_value=expected_payload):
            result = await middleware._validate_jwt("some.jwt.token")

        assert result == expected_payload

    @pytest.mark.asyncio
    async def test_validate_jwt_creates_jwks_client_lazily(self):
        """_validate_jwt must create a PyJWKClient when _jwks_client is None."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        # Pre-set jwks_uri but leave _jwks_client as None
        middleware._jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        middleware._jwks_client = None

        mock_jwks_client_instance = MagicMock()
        mock_jwks_client_instance.get_signing_key_from_jwt.side_effect = Exception(
            "no key"
        )

        with patch(
            "app.middleware.auth.PyJWKClient", return_value=mock_jwks_client_instance
        ):
            result = await middleware._validate_jwt("some.jwt.token")

        # Client should have been created
        assert middleware._jwks_client is mock_jwks_client_instance
        assert result is None  # key fetch failed → None

    @pytest.mark.asyncio
    async def test_validate_jwt_with_unknown_kid_returns_none(self):
        """JWT with a key ID not present in JWKS must fail validation and return None."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = "https://idp.example.com/"
            mock_settings.oidc_client_id = "test-client-id"
            mock_settings.auth_username = None
            mock_settings.auth_password = None

            middleware = AuthMiddleware(MagicMock())

        middleware._jwks_uri = "https://idp.example.com/.well-known/jwks.json"

        # Simulate PyJWKClient raising when the kid is not found
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt.side_effect = Exception(
            "Unable to find a signing key that matches"
        )
        middleware._jwks_client = mock_jwks_client

        payload = await middleware._validate_jwt("token.with.unknown.kid")

        assert payload is None


class TestBasicAuthMalformedBase64:
    """Tests for malformed base64 in Basic Auth — error handling for invalid credentials."""

    @pytest.mark.asyncio
    async def test_malformed_base64_returns_401(self):
        """Malformed base64 in the Authorization header must return 401."""
        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "user"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "pass"

            middleware = AuthMiddleware(MagicMock())

        # "Basic " followed by invalid base64 (not valid UTF-8 after decode)
        request = RequestBuilder.create_mock_request(
            "/protected",
            {"Authorization": "Basic !!!not-valid-base64!!!"},
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_basic_auth_with_no_colon_separator_returns_401(self):
        """Basic Auth credentials without ':' separator must return 401 (wrong password)."""
        import base64

        with patch("app.middleware.auth.settings") as mock_settings:
            mock_settings.oidc_discovery_url = None
            mock_settings.auth_username = "user"
            mock_settings.auth_password = MagicMock()
            mock_settings.auth_password.get_secret_value.return_value = "pass"

            middleware = AuthMiddleware(MagicMock())

        # Valid base64 but no colon — partition returns ("nocolon", "", "")
        encoded = base64.b64encode(b"nocolon").decode()
        request = RequestBuilder.create_mock_request(
            "/protected",
            {"Authorization": f"Basic {encoded}"},
        )

        async def mock_call_next(req):
            return JSONResponse({"error": "should not reach here"})

        response = await middleware.dispatch(request, mock_call_next)

        # username="nocolon", password="" — won't match "user"/"pass"
        assert response.status_code == 401
