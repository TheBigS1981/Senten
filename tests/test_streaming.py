"""Integration tests for the SSE streaming endpoints.

Tests cover:
  POST /api/translate/stream
  POST /api/write/stream

Both endpoints only work with engine='llm'. DeepL has no streaming API.

SSE event format:
  data: {"chunk": "<text>"}\\n\\n                          — incremental chunk
  data: {"done": true, "detected_source_lang": "<code>"}\\n\\n  — final (translate)
  data: {"done": true}\\n\\n                                — final (write)
  data: {"error": "<message>"}\\n\\n                        — on error

The LLM service singleton is patched at the router level so no real LLM
calls are made. The rate limiter is bypassed via TESTING=true (set in
conftest.py via the app startup).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse_events(raw: str) -> list[dict]:
    """Parse a raw SSE response body into a list of decoded JSON payloads."""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


async def _make_translate_stream_generator(*chunks: str, detected_lang: str = "EN"):
    """Async generator that yields SSE-formatted translate stream events."""
    for chunk in chunks:
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    yield f"data: {json.dumps({'done': True, 'detected_source_lang': detected_lang})}\n\n"


async def _make_write_stream_generator(*chunks: str):
    """Async generator that yields SSE-formatted write stream events."""
    for chunk in chunks:
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


# ---------------------------------------------------------------------------
# POST /api/translate/stream — error cases (HTTP errors before streaming)
# ---------------------------------------------------------------------------


class TestTranslateStreamErrorCases:
    def test_returns_400_when_engine_is_deepl(self, client):
        """Streaming is only available for engine='llm'; deepl → 400."""
        res = client.post(
            "/api/translate/stream",
            json={"text": "Hello", "target_lang": "DE", "engine": "deepl"},
        )
        assert res.status_code == 400
        assert "ERR_STREAMING_LLM_ONLY" in res.json()["detail"]

    def test_returns_4xx_when_text_is_empty(self, client):
        """Empty text must be rejected before streaming starts.

        Pydantic's min_length=1 fires first (422) when text is literally empty.
        Our own 400 guard fires when text is non-empty but strips to empty.
        Both are acceptable — the important thing is that no stream is started.
        """
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True

            res = client.post(
                "/api/translate/stream",
                json={"text": "", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code in (400, 422)

    def test_returns_400_when_text_is_whitespace_only(self, client):
        """Whitespace-only text is treated as empty after strip()."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True

            res = client.post(
                "/api/translate/stream",
                json={"text": "   \n\t  ", "target_lang": "DE", "engine": "llm"},
            )

        # 400 from our guard or 422 from Pydantic str_strip_whitespace
        assert res.status_code in (400, 422)

    def test_returns_503_when_llm_not_configured(self, client):
        """LLM not configured → 503 before any streaming begins."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = False

            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 503
        assert "ERR_LLM_NOT_CONFIGURED" in res.json()["detail"]

    def test_returns_422_when_engine_value_is_invalid(self, client):
        """Pydantic rejects unknown engine values with 422."""
        res = client.post(
            "/api/translate/stream",
            json={"text": "Hello", "target_lang": "DE", "engine": "unknown"},
        )
        assert res.status_code == 422

    def test_returns_422_when_text_field_is_missing(self, client):
        """Missing required 'text' field → 422 from Pydantic."""
        res = client.post(
            "/api/translate/stream",
            json={"target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/translate/stream — mid-stream errors and language validation
# ---------------------------------------------------------------------------


class TestTranslateStream:
    def test_error_event_after_partial_chunk(self, client):
        """Mid-stream error: partial chunk appears before error event; no done event follows."""

        async def _error_mid_stream():
            yield f"data: {json.dumps({'chunk': 'Partial'})}\n\n"
            yield f"data: {json.dumps({'error': 'LLM connection lost'})}\n\n"

        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _error_mid_stream()

            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        events = _parse_sse_events(res.text)
        assert any("chunk" in e for e in events), "Expected at least one chunk event"
        assert any("error" in e for e in events), "Expected an error event"
        assert not any(e.get("done") for e in events), (
            "No done event expected after error"
        )

    def test_invalid_target_lang_returns_422(self, client):
        """Invalid target language returns 422 before streaming begins."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "INVALID_LANG", "engine": "llm"},
            )
        assert res.status_code == 422

    def test_invalid_source_lang_returns_422(self, client):
        """Invalid source language returns 422 before streaming begins."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            res = client.post(
                "/api/translate/stream",
                json={
                    "text": "Hello",
                    "target_lang": "DE",
                    "source_lang": "INVALID",
                    "engine": "llm",
                },
            )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/translate/stream — happy path
# ---------------------------------------------------------------------------


class TestTranslateStreamHappyPath:
    def test_returns_200_with_sse_content_type(self, client):
        """Successful streaming response has text/event-stream content-type."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Hallo", " Welt"
            )

            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello World", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

    def test_streams_chunks_correctly(self, client):
        """Three chunks are streamed in order before the done event."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Hallo", " schöne", " Welt", detected_lang="EN"
            )

            res = client.post(
                "/api/translate/stream",
                json={
                    "text": "Hello beautiful world",
                    "target_lang": "DE",
                    "engine": "llm",
                },
            )

        assert res.status_code == 200
        events = _parse_sse_events(res.text)

        # First three events are chunks
        assert events[0] == {"chunk": "Hallo"}
        assert events[1] == {"chunk": " schöne"}
        assert events[2] == {"chunk": " Welt"}

    def test_done_event_contains_detected_source_lang(self, client):
        """The final SSE event must include detected_source_lang."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Bonjour", detected_lang="EN"
            )

            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "FR", "engine": "llm"},
            )

        events = _parse_sse_events(res.text)
        done_events = [e for e in events if e.get("done") is True]

        assert len(done_events) == 1
        assert done_events[0]["detected_source_lang"] == "EN"

    def test_done_event_is_last_event(self, client):
        """The done event must be the final event in the stream."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "chunk1", "chunk2", detected_lang="DE"
            )

            res = client.post(
                "/api/translate/stream",
                json={"text": "Text", "target_lang": "EN-GB", "engine": "llm"},
            )

        events = _parse_sse_events(res.text)
        assert events[-1].get("done") is True

    def test_translate_stream_calls_service_with_correct_args(self, client):
        """translate_stream is called with text, target_lang, and source_lang."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Hallo", detected_lang="EN"
            )

            client.post(
                "/api/translate/stream",
                json={
                    "text": "Hello",
                    "target_lang": "DE",
                    "source_lang": "EN",
                    "engine": "llm",
                },
            )

        mock_llm.translate_stream.assert_called_once_with(
            text="Hello",
            target_lang="DE",
            source_lang="EN",
        )

    def test_translate_stream_passes_none_source_lang_when_not_provided(self, client):
        """source_lang defaults to None when not provided in the request."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Hallo", detected_lang="EN"
            )

            client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        mock_llm.translate_stream.assert_called_once_with(
            text="Hello",
            target_lang="DE",
            source_lang=None,
        )

    def test_no_cache_header_is_set(self, client):
        """SSE responses must have Cache-Control: no-cache."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate_stream.return_value = _make_translate_stream_generator(
                "Hallo"
            )

            res = client.post(
                "/api/translate/stream",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.headers.get("cache-control") == "no-cache"


# ---------------------------------------------------------------------------
# POST /api/write/stream — error cases (HTTP errors before streaming)
# ---------------------------------------------------------------------------


class TestWriteStreamErrorCases:
    def test_returns_400_when_engine_is_deepl(self, client):
        """Streaming is only available for engine='llm'; deepl → 400."""
        res = client.post(
            "/api/write/stream",
            json={"text": "Some text.", "target_lang": "DE", "engine": "deepl"},
        )
        assert res.status_code == 400
        assert "ERR_STREAMING_LLM_ONLY" in res.json()["detail"]

    def test_returns_4xx_when_text_is_empty(self, client):
        """Empty text must be rejected before streaming starts.

        Pydantic's min_length=1 fires first (422) when text is literally empty.
        Our own 400 guard fires when text is non-empty but strips to empty.
        Both are acceptable — the important thing is that no stream is started.
        """
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True

            res = client.post(
                "/api/write/stream",
                json={"text": "", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code in (400, 422)

    def test_returns_400_when_text_is_whitespace_only(self, client):
        """Whitespace-only text is treated as empty after strip()."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True

            res = client.post(
                "/api/write/stream",
                json={"text": "   ", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code in (400, 422)

    def test_returns_503_when_llm_not_configured(self, client):
        """LLM not configured → 503 before any streaming begins."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = False

            res = client.post(
                "/api/write/stream",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 503
        assert "ERR_LLM_NOT_CONFIGURED" in res.json()["detail"]

    def test_returns_422_when_engine_value_is_invalid(self, client):
        """Pydantic rejects unknown engine values with 422."""
        res = client.post(
            "/api/write/stream",
            json={"text": "Some text.", "target_lang": "DE", "engine": "unknown"},
        )
        assert res.status_code == 422

    def test_returns_422_when_text_field_is_missing(self, client):
        """Missing required 'text' field → 422 from Pydantic."""
        res = client.post(
            "/api/write/stream",
            json={"target_lang": "DE", "engine": "llm"},
        )
        assert res.status_code == 422

    def test_invalid_target_lang_returns_422(self, client):
        """Invalid target language returns 422 before streaming begins."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            res = client.post(
                "/api/write/stream",
                json={"text": "Hello", "target_lang": "INVALID_LANG", "engine": "llm"},
            )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/write/stream — happy path
# ---------------------------------------------------------------------------


class TestWriteStreamHappyPath:
    def test_returns_200_with_sse_content_type(self, client):
        """Successful streaming response has text/event-stream content-type."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "Verbesserter", " Text"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Schlechter Text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

    def test_streams_chunks_correctly(self, client):
        """Two chunks are streamed in order before the done event."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "Improved", " text"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Bad text.", "target_lang": "EN-US", "engine": "llm"},
            )

        assert res.status_code == 200
        events = _parse_sse_events(res.text)

        assert events[0] == {"chunk": "Improved"}
        assert events[1] == {"chunk": " text"}

    def test_done_event_has_no_detected_source_lang(self, client):
        """Write stream done event contains only 'done: true' — no detected_source_lang."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "chunk"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        events = _parse_sse_events(res.text)
        done_events = [e for e in events if e.get("done") is True]

        assert len(done_events) == 1
        assert "detected_source_lang" not in done_events[0]

    def test_done_event_is_last_event(self, client):
        """The done event must be the final event in the stream."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "chunk1", "chunk2"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        events = _parse_sse_events(res.text)
        assert events[-1].get("done") is True

    def test_write_stream_calls_service_with_correct_args(self, client):
        """write_optimize_stream is called with text and target_lang."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "Optimiert"
            )

            client.post(
                "/api/write/stream",
                json={"text": "Schlechter Text", "target_lang": "DE", "engine": "llm"},
            )

        mock_llm.write_optimize_stream.assert_called_once_with(
            text="Schlechter Text",
            target_lang="DE",
        )

    def test_no_cache_header_is_set(self, client):
        """SSE responses must have Cache-Control: no-cache."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "chunk"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Some text.", "target_lang": "DE", "engine": "llm"},
            )

        assert res.headers.get("cache-control") == "no-cache"

    def test_total_event_count_matches_chunks_plus_done(self, client):
        """Total SSE events = number of chunks + 1 done event."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize_stream.return_value = _make_write_stream_generator(
                "a", "b"
            )

            res = client.post(
                "/api/write/stream",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        events = _parse_sse_events(res.text)
        assert len(events) == 3  # 2 chunks + 1 done
