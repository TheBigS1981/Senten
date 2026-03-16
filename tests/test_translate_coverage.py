"""Coverage tests for app/routers/translate.py — closing the remaining gaps.

Targets the following missing lines (from pytest --cov-report=term-missing):
  106          — empty text → 400 in /translate
  114-139      — LLM engine paths in /translate
  195-196      — DeepL error handling in /translate
  240          — empty text → 400 in /write
  289-290      — DeepL error handling in /write
  314          — empty text → 400 in /translate/stream
  361-362      — empty text → 400 in /write/stream
  397          — /translate/stream: engine != 'llm' → 400
  415          — /translate/stream: LLM not configured → 503
  459          — /write/stream: engine != 'llm' → 400
  477          — /write/stream: LLM not configured → 503

All LLM service calls are mocked — no real provider is contacted.
DeepL service calls are patched via patch.object(deepl_service, ...).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import deepl.exceptions
import pytest
from fastapi import HTTPException

from app.models.schemas import TranslateRequest, WriteRequest
from app.routers.translate import (
    _handle_llm_error,
    _stream_with_usage,
    translate_stream,
    translate_text,
    write_optimize,
    write_stream,
)
from app.services.deepl_service import deepl_service
from app.services.llm_service import (
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMModelError,
    LLMQuotaError,
    LLMTimeoutError,
    llm_service,
)

# ---------------------------------------------------------------------------
# Shared mock return values
# ---------------------------------------------------------------------------

_TRANSLATE_RESULT = {
    "translated_text": "Hallo Welt",
    "detected_source_lang": "EN",
    "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
}

_TRANSLATE_RESULT_NO_USAGE = {
    "translated_text": "Hallo Welt",
    "detected_source_lang": "EN",
    # no 'usage' key
}

_WRITE_RESULT = {
    "optimized_text": "Optimierter Text",
    "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
}


# ---------------------------------------------------------------------------
# POST /api/translate — line 106: empty text → 400
# ---------------------------------------------------------------------------


class TestTranslateEmptyText:
    """Empty text validation in POST /api/translate."""

    def test_whitespace_only_text_returns_422_from_pydantic(self, client):
        """Whitespace-only text is rejected by Pydantic before reaching the router."""
        # Pydantic min_length rejects this before the router guard
        res = client.post("/api/translate", json={"text": " ", "target_lang": "DE"})
        assert res.status_code == 422
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/translate — lines 114-139: LLM engine paths
# (These are already covered by test_llm_router.py but we add targeted tests
#  for the specific sub-paths that remain uncovered.)
# ---------------------------------------------------------------------------


class TestTranslateLLMPaths:
    """Lines 114-139: LLM engine paths in POST /api/translate."""

    def test_llm_not_configured_returns_503(self, client):
        """Line 114-116: LLM not configured → 503."""
        with patch.object(llm_service, "is_configured", return_value=False):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()

    def test_llm_text_too_long_returns_413(self, client):
        """Lines 117-120: text exceeding llm_max_input_chars → 413."""
        from app.config import settings

        long_text = "x" * (settings.llm_max_input_chars + 1)
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/translate",
                json={"text": long_text, "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 413
        assert "detail" in res.json()

    def test_llm_invalid_target_lang_returns_422(self, client):
        """Line 121: invalid target language → 422 via _validate_llm_languages."""
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "INVALID_LANG", "engine": "llm"},
            )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_llm_invalid_source_lang_returns_422(self, client):
        """Line 121: invalid source language → 422 via _validate_llm_languages."""
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/translate",
                json={
                    "text": "Hello",
                    "target_lang": "DE",
                    "source_lang": "INVALID",
                    "engine": "llm",
                },
            )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_llm_translate_success_with_usage(self, client):
        """Lines 122-133: successful LLM translate with usage field."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "translate", new_callable=AsyncMock
            ) as mock_translate,
        ):
            mock_translate.return_value = _TRANSLATE_RESULT
            res = client.post(
                "/api/translate",
                json={"text": "Hello world", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["translated_text"] == "Hallo Welt"
        assert data["characters_used"] == len("Hello world")
        assert data["usage"] == {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }

    def test_llm_translate_success_without_usage(self, client):
        """Lines 127-133: successful LLM translate without usage field → usage=None."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "translate", new_callable=AsyncMock
            ) as mock_translate,
        ):
            mock_translate.return_value = _TRANSLATE_RESULT_NO_USAGE
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["translated_text"] == "Hallo Welt"
        assert data.get("usage") is None

    def test_llm_translate_llm_error_returns_502(self, client):
        """Lines 136-139: generic LLMError → 502 Bad Gateway."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "translate", new_callable=AsyncMock
            ) as mock_translate,
        ):
            mock_translate.side_effect = LLMError("generic llm error")
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 502
        assert "detail" in res.json()

    def test_llm_translate_model_error_returns_422(self, client):
        """LLMModelError → 422 Unprocessable Content."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "translate", new_callable=AsyncMock
            ) as mock_translate,
        ):
            mock_translate.side_effect = LLMModelError("model not found")
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 422
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/translate — lines 195-196: DeepL error handling
# ---------------------------------------------------------------------------


class TestTranslateDeepLErrors:
    """Lines 195-196: DeepL exception handling in POST /api/translate."""

    def test_deepl_too_many_requests_returns_429(self, client):
        """TooManyRequestsException from DeepL → 429."""
        with patch.object(
            deepl_service,
            "translate",
            side_effect=deepl.exceptions.TooManyRequestsException("rate limit"),
        ):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE"},
            )
        assert res.status_code == 429
        assert "detail" in res.json()

    def test_deepl_quota_exceeded_returns_422(self, client):
        """QuotaExceededException from DeepL → 422."""
        with patch.object(
            deepl_service,
            "translate",
            side_effect=deepl.exceptions.QuotaExceededException("quota"),
        ):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE"},
            )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_deepl_auth_error_returns_401(self, client):
        """AuthorizationException from DeepL → 401."""
        with patch.object(
            deepl_service,
            "translate",
            side_effect=deepl.exceptions.AuthorizationException("bad key"),
        ):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE"},
            )
        assert res.status_code == 401
        assert "detail" in res.json()

    def test_deepl_generic_exception_returns_503(self, client):
        """Generic DeepLException → 503."""
        with patch.object(
            deepl_service,
            "translate",
            side_effect=deepl.exceptions.DeepLException("some deepl error"),
        ):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()

    def test_deepl_unexpected_exception_returns_503(self, client):
        """Completely unexpected exception (not DeepL) → 503."""
        with patch.object(
            deepl_service,
            "translate",
            side_effect=RuntimeError("unexpected"),
        ):
            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/write — line 240: empty text → 400
# ---------------------------------------------------------------------------


class TestWriteEmptyText:
    """Empty text validation in POST /api/write."""

    def test_whitespace_only_text_returns_422_from_pydantic(self, client):
        """Whitespace-only text is rejected by Pydantic before reaching the router."""
        # Pydantic min_length rejects this before the router guard
        res = client.post("/api/write", json={"text": " ", "target_lang": "DE"})
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_empty_string_returns_422_from_pydantic(self, client):
        """Explicit empty string is rejected by Pydantic min_length validation."""
        # Pydantic min_length rejects this before the router guard
        res = client.post("/api/write", json={"text": "", "target_lang": "DE"})
        assert res.status_code == 422
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/write — lines 289-290: DeepL error handling
# ---------------------------------------------------------------------------


class TestWriteDeepLErrors:
    """Lines 289-290: DeepL exception handling in POST /api/write."""

    def test_deepl_too_many_requests_returns_429(self, client):
        """TooManyRequestsException from DeepL write_optimize → 429."""
        with patch.object(
            deepl_service,
            "write_optimize",
            side_effect=deepl.exceptions.TooManyRequestsException("rate limit"),
        ):
            res = client.post(
                "/api/write",
                json={"text": "Some text to optimize.", "target_lang": "DE"},
            )
        assert res.status_code == 429
        assert "detail" in res.json()

    def test_deepl_quota_exceeded_returns_422(self, client):
        """QuotaExceededException from DeepL write_optimize → 422."""
        with patch.object(
            deepl_service,
            "write_optimize",
            side_effect=deepl.exceptions.QuotaExceededException("quota"),
        ):
            res = client.post(
                "/api/write",
                json={"text": "Some text to optimize.", "target_lang": "DE"},
            )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_deepl_auth_error_returns_401(self, client):
        """AuthorizationException from DeepL write_optimize → 401."""
        with patch.object(
            deepl_service,
            "write_optimize",
            side_effect=deepl.exceptions.AuthorizationException("bad key"),
        ):
            res = client.post(
                "/api/write",
                json={"text": "Some text to optimize.", "target_lang": "DE"},
            )
        assert res.status_code == 401
        assert "detail" in res.json()

    def test_deepl_generic_exception_returns_503(self, client):
        """Generic DeepLException from write_optimize → 503."""
        with patch.object(
            deepl_service,
            "write_optimize",
            side_effect=deepl.exceptions.DeepLException("deepl error"),
        ):
            res = client.post(
                "/api/write",
                json={"text": "Some text to optimize.", "target_lang": "DE"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()

    def test_unexpected_exception_returns_503(self, client):
        """Completely unexpected exception from write_optimize → 503."""
        with patch.object(
            deepl_service,
            "write_optimize",
            side_effect=RuntimeError("unexpected"),
        ):
            res = client.post(
                "/api/write",
                json={"text": "Some text to optimize.", "target_lang": "DE"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/translate/stream — line 314: empty text → 400
# ---------------------------------------------------------------------------


class TestTranslateStreamEmptyText:
    """Empty text validation in POST /api/translate/stream."""

    def test_empty_text_returns_422_from_pydantic(self, client):
        """Empty text in streaming translate is rejected by Pydantic min_length."""
        # Pydantic min_length rejects this before the router guard
        res = client.post(
            "/api/translate/stream",
            json={"text": "", "target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_whitespace_only_text_returns_422_from_pydantic(self, client):
        """Whitespace-only text in streaming translate is rejected by Pydantic."""
        # Pydantic min_length rejects this before the router guard
        res = client.post(
            "/api/translate/stream",
            json={"text": "   ", "target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/write/stream — lines 361-362: empty text → 400
# ---------------------------------------------------------------------------


class TestWriteStreamEmptyText:
    """Empty text validation in POST /api/write/stream."""

    def test_empty_text_returns_422_from_pydantic(self, client):
        """Empty text in streaming write is rejected by Pydantic min_length."""
        # Pydantic min_length rejects this before the router guard
        res = client.post(
            "/api/write/stream",
            json={"text": "", "target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_whitespace_only_text_returns_422_from_pydantic(self, client):
        """Whitespace-only text in streaming write is rejected by Pydantic."""
        # Pydantic min_length rejects this before the router guard
        res = client.post(
            "/api/write/stream",
            json={"text": "   ", "target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/translate/stream — line 397: engine != 'llm' → 400
# ---------------------------------------------------------------------------


class TestTranslateStreamEngineValidation:
    """/translate/stream only supports engine='llm' — non-LLM engines must be rejected."""

    def test_deepl_engine_returns_400(self, client):
        """Requesting streaming with engine='deepl' must return 400."""
        res = client.post(
            "/api/translate/stream",
            json={"text": "Hello world", "target_lang": "DE", "engine": "deepl"},
        )
        assert res.status_code == 400
        assert "detail" in res.json()

    def test_default_engine_returns_400(self, client):
        """Requesting streaming without specifying engine='llm' must return 400."""
        res = client.post(
            "/api/translate/stream",
            # No engine field — defaults to 'deepl'
            json={"text": "Hello world", "target_lang": "DE"},
        )
        assert res.status_code == 400
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/translate/stream — line 415: LLM not configured → 503
# ---------------------------------------------------------------------------


class TestTranslateStreamLLMNotConfigured:
    """Line 415: /translate/stream with LLM not configured → 503."""

    def test_llm_not_configured_returns_503(self, client):
        """When LLM is not configured, streaming translate must return 503."""
        with patch.object(llm_service, "is_configured", return_value=False):
            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello world", "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/write/stream — line 459: engine != 'llm' → 400
# ---------------------------------------------------------------------------


class TestWriteStreamEngineValidation:
    """/write/stream only supports engine='llm' — non-LLM engines must be rejected."""

    def test_deepl_engine_returns_400(self, client):
        """Requesting write streaming with engine='deepl' must return 400."""
        res = client.post(
            "/api/write/stream",
            json={"text": "Some text.", "target_lang": "DE", "engine": "deepl"},
        )
        assert res.status_code == 400
        assert "detail" in res.json()

    def test_default_engine_returns_400(self, client):
        """Requesting write streaming without engine='llm' must return 400."""
        res = client.post(
            "/api/write/stream",
            json={"text": "Some text.", "target_lang": "DE"},
        )
        assert res.status_code == 400
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# POST /api/write/stream — line 477: LLM not configured → 503
# ---------------------------------------------------------------------------


class TestWriteStreamLLMNotConfigured:
    """Line 477: /write/stream with LLM not configured → 503."""

    def test_llm_not_configured_returns_503(self, client):
        """When LLM is not configured, streaming write must return 503."""
        with patch.object(llm_service, "is_configured", return_value=False):
            res = client.post(
                "/api/write/stream",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# Additional edge cases for completeness
# ---------------------------------------------------------------------------


class TestTranslateStreamTextTooLong:
    """Streaming endpoints must also enforce llm_max_input_chars."""

    def test_translate_stream_text_too_long_returns_413(self, client):
        """Text exceeding llm_max_input_chars in /translate/stream → 413."""
        from app.config import settings

        long_text = "x" * (settings.llm_max_input_chars + 1)
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/translate/stream",
                json={"text": long_text, "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 413
        assert "detail" in res.json()

    def test_write_stream_text_too_long_returns_413(self, client):
        """Text exceeding llm_max_input_chars in /write/stream → 413."""
        from app.config import settings

        long_text = "x" * (settings.llm_max_input_chars + 1)
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/write/stream",
                json={"text": long_text, "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 413
        assert "detail" in res.json()


# ---------------------------------------------------------------------------
# _handle_llm_error — line 106: non-LLMError exception → 503
# ---------------------------------------------------------------------------


class TestHandleLlmErrorFallback:
    """_handle_llm_error — maps exception types to correct HTTP status codes."""

    def test_non_llm_error_returns_503(self):
        """A plain Exception (not LLMError subclass) must map to 503."""
        exc = ValueError("something unexpected")
        result = _handle_llm_error(exc, "user-1", "Übersetzung")

        assert result.status_code == 503
        assert result.detail

    def test_llm_error_base_class_returns_502(self):
        """A base LLMError (not a specific subclass) must map to 502."""
        exc = LLMError("generic llm error")
        result = _handle_llm_error(exc, "user-1", "Übersetzung")

        assert result.status_code == 502


# ---------------------------------------------------------------------------
# _stream_with_usage — lines 195-196: JSON decode error in SSE stream
# ---------------------------------------------------------------------------


class TestStreamWithUsageJsonError:
    """_stream_with_usage — malformed JSON handling and usage recording behavior."""

    @pytest.mark.asyncio
    async def test_malformed_json_in_chunk_does_not_block_done_event(self):
        """Malformed JSON in a chunk must not prevent usage recording when done event follows."""

        async def gen():
            yield 'data: {"chunk": "Hello"}\n\n'
            yield "data: {not valid json}\n\n"
            yield 'data: {"done": true}\n\n'

        with patch("app.routers.translate._record_usage") as mock_record:
            chunks = [
                c
                async for c in _stream_with_usage(
                    gen(),
                    user_id="u1",
                    text="Hello",
                    op_type="translate",
                    target_lang="DE",
                )
            ]

        # All 3 chunks must be yielded (malformed JSON is skipped, not dropped)
        assert len(chunks) == 3
        mock_record.assert_called_once_with(
            "u1",
            "Hello",
            "translate",
            "DE",
            word_count=1,
            input_tokens=0,
            output_tokens=0,
        )

    @pytest.mark.asyncio
    async def test_non_data_lines_do_not_trigger_done(self):
        """Lines not starting with 'data: ' must be ignored when checking for done event."""

        async def gen():
            yield "event: update\n"
            yield 'data: {"chunk": "world"}\n\n'
            # No done event → usage NOT recorded

        with patch("app.routers.translate._record_usage") as mock_record:
            chunks = [
                c
                async for c in _stream_with_usage(
                    gen(),
                    user_id="u2",
                    text="world",
                    op_type="write",
                    target_lang="EN-US",
                )
            ]

        assert len(chunks) == 2
        mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# Router empty-text guards — direct unit tests bypassing Pydantic
# (Lines 106, 240, 314, 397, 459 are defence-in-depth guards that Pydantic
#  catches first in normal HTTP flow. We test them directly via the router
#  functions to ensure the guard logic itself is covered.)
# ---------------------------------------------------------------------------


class TestRouterEmptyTextGuardsDirect:
    """Direct unit tests for the router-level empty-text guards.

    Pydantic's str_strip_whitespace=True + min_length=1 prevents whitespace-only
    strings from reaching the router in normal HTTP flow. These tests call the
    router functions directly with a mocked request body to cover the guards.
    """

    @pytest.mark.asyncio
    async def test_translate_empty_text_guard_raises_400(self):
        """translate_text raises 400 when text strips to empty string."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        # Bypass Pydantic by constructing the model with a non-empty string,
        # then monkey-patching .text to return empty after strip
        body = MagicMock(spec=TranslateRequest)
        body.text = "   "  # will strip to ""
        body.engine = "deepl"
        body.target_lang = "DE"
        body.source_lang = None

        with pytest.raises(HTTPException) as exc_info:
            await translate_text(mock_request, body)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_write_empty_text_guard_raises_400(self):
        """write_optimize raises 400 when text strips to empty string."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        body = MagicMock(spec=WriteRequest)
        body.text = "   "  # will strip to ""
        body.engine = "deepl"
        body.target_lang = "DE"

        with pytest.raises(HTTPException) as exc_info:
            await write_optimize(mock_request, body)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_translate_stream_empty_text_guard_raises_400(self):
        """translate_stream raises 400 when text strips to empty string."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        body = MagicMock(spec=TranslateRequest)
        body.text = "   "  # will strip to ""
        body.engine = "llm"
        body.target_lang = "DE"
        body.source_lang = None

        with pytest.raises(HTTPException) as exc_info:
            await translate_stream(mock_request, body)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_translate_stream_non_llm_engine_guard_raises_400(self):
        """translate_stream raises 400 when engine is not 'llm'."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        body = MagicMock(spec=TranslateRequest)
        body.text = "Hello world"  # non-empty
        body.engine = "deepl"  # not 'llm'
        body.target_lang = "DE"
        body.source_lang = None

        with pytest.raises(HTTPException) as exc_info:
            await translate_stream(mock_request, body)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_write_stream_empty_text_guard_raises_400(self):
        """write_stream raises 400 when text strips to empty string."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        body = MagicMock(spec=WriteRequest)
        body.text = "   "  # will strip to ""
        body.engine = "llm"
        body.target_lang = "DE"

        with pytest.raises(HTTPException) as exc_info:
            await write_stream(mock_request, body)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_write_stream_non_llm_engine_guard_raises_400(self):
        """write_stream raises 400 when engine is not 'llm'."""
        mock_request = MagicMock()
        mock_request.state.user_id = "test-user"

        body = MagicMock(spec=WriteRequest)
        body.text = "Some text"  # non-empty
        body.engine = "deepl"  # not 'llm'
        body.target_lang = "DE"

        with pytest.raises(HTTPException) as exc_info:
            await write_stream(mock_request, body)

        assert exc_info.value.status_code == 400


class TestWriteLLMPaths:
    """LLM engine paths in POST /api/write — parallel to translate LLM paths."""

    def test_llm_not_configured_returns_503(self, client):
        """LLM not configured for write → 503."""
        with patch.object(llm_service, "is_configured", return_value=False):
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 503
        assert "detail" in res.json()

    def test_llm_text_too_long_returns_413(self, client):
        """Text exceeding llm_max_input_chars for write → 413."""
        from app.config import settings

        long_text = "x" * (settings.llm_max_input_chars + 1)
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/write",
                json={"text": long_text, "target_lang": "DE", "engine": "llm"},
            )
        assert res.status_code == 413
        assert "detail" in res.json()

    def test_llm_invalid_target_lang_returns_422(self, client):
        """Invalid target language for LLM write → 422."""
        with patch.object(llm_service, "is_configured", return_value=True):
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "INVALID", "engine": "llm"},
            )
        assert res.status_code == 422
        assert "detail" in res.json()

    def test_llm_write_success_with_usage(self, client):
        """Successful LLM write with usage field → 200."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.return_value = _WRITE_RESULT
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["optimized_text"] == "Optimierter Text"
        assert data["usage"] == {
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
        }

    def test_llm_write_success_without_usage(self, client):
        """Successful LLM write without usage field → usage=None."""
        result_no_usage = {"optimized_text": "Optimierter Text"}
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.return_value = result_no_usage
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["optimized_text"] == "Optimierter Text"
        assert data.get("usage") is None

    def test_llm_write_timeout_returns_408(self, client):
        """LLMTimeoutError from write_optimize → 408."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.side_effect = LLMTimeoutError("timeout")
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 408
        assert "detail" in res.json()

    def test_llm_write_auth_error_returns_401(self, client):
        """LLMAuthError from write_optimize → 401."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.side_effect = LLMAuthError("bad key")
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 401
        assert "detail" in res.json()

    def test_llm_write_quota_error_returns_429(self, client):
        """LLMQuotaError from write_optimize → 429."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.side_effect = LLMQuotaError("quota exceeded")
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 429
        assert "detail" in res.json()

    def test_llm_write_connection_error_returns_503(self, client):
        """LLMConnectionError from write_optimize → 503."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.side_effect = LLMConnectionError("unreachable")
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 503
        assert "detail" in res.json()

    def test_llm_write_generic_llm_error_returns_502(self, client):
        """Generic LLMError from write_optimize → 502."""
        with (
            patch.object(llm_service, "is_configured", return_value=True),
            patch.object(
                llm_service, "write_optimize", new_callable=AsyncMock
            ) as mock_write,
        ):
            mock_write.side_effect = LLMError("generic error")
            res = client.post(
                "/api/write",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 502
        assert "detail" in res.json()
