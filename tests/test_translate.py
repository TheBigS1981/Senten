"""Integration tests for the /api/translate and /api/write endpoints.

All tests run with DeepL in mock mode (DEEPL_API_KEY="" — see conftest.py).
No real API calls are made.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# /api/config
# ---------------------------------------------------------------------------


def test_config_returns_configured_status(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert "mock_mode" in data


# ---------------------------------------------------------------------------
# /api/translate
# ---------------------------------------------------------------------------


def test_translate_returns_200_in_mock_mode(client):
    res = client.post(
        "/api/translate", json={"text": "Hello world", "target_lang": "DE"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "translated_text" in data
    assert "characters_used" in data
    assert data["characters_used"] > 0


def test_translate_mock_text_contains_prefix(client):
    """Mock mode prepends '[Mock <lang>]' to the output."""
    res = client.post("/api/translate", json={"text": "Hello", "target_lang": "DE"})
    assert res.status_code == 200
    assert "[Mock DE]" in res.json()["translated_text"]


def test_translate_empty_text_returns_400(client):
    res = client.post("/api/translate", json={"text": "", "target_lang": "DE"})
    assert res.status_code in (400, 422)


def test_translate_whitespace_only_returns_4xx(client):
    # str_strip_whitespace=True causes Pydantic to strip then fail min_length → 422
    res = client.post("/api/translate", json={"text": "   \n\t  ", "target_lang": "DE"})
    assert res.status_code in (400, 422)


def test_translate_text_too_long_returns_4xx(client):
    # Pydantic max_length validation raises 422 Unprocessable Entity
    res = client.post("/api/translate", json={"text": "x" * 10001, "target_lang": "DE"})
    assert res.status_code == 422


def test_translate_missing_text_returns_422(client):
    res = client.post("/api/translate", json={"target_lang": "DE"})
    assert res.status_code == 422


def test_translate_various_target_languages(client):
    for lang in ("DE", "EN-GB", "EN-US", "FR", "ES"):
        res = client.post("/api/translate", json={"text": "Test", "target_lang": lang})
        assert res.status_code == 200, f"Failed for target_lang={lang}"


def test_translate_with_source_lang(client):
    res = client.post(
        "/api/translate",
        json={"text": "Hallo", "source_lang": "DE", "target_lang": "EN-GB"},
    )
    assert res.status_code == 200


def test_translate_does_not_expose_internal_errors(client):
    """Error responses must not leak internal details."""
    res = client.post("/api/translate", json={"text": "", "target_lang": "DE"})
    # Even on error, response should be JSON with 'detail' key (not a raw exception)
    assert res.status_code in (400, 422, 503)
    body = res.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# /api/write
# ---------------------------------------------------------------------------


def test_write_returns_200_in_mock_mode(client):
    res = client.post(
        "/api/write", json={"text": "This is a test.", "target_lang": "DE"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "optimized_text" in data
    assert "characters_used" in data


def test_write_mock_text_contains_prefix(client):
    res = client.post("/api/write", json={"text": "Some text.", "target_lang": "DE"})
    assert res.status_code == 200
    assert "[Optimiert Mock]" in res.json()["optimized_text"]


def test_write_empty_text_returns_400(client):
    res = client.post("/api/write", json={"text": "", "target_lang": "DE"})
    assert res.status_code in (400, 422)


def test_write_text_too_long_returns_4xx(client):
    # Pydantic max_length validation raises 422 Unprocessable Entity
    res = client.post("/api/write", json={"text": "x" * 10001, "target_lang": "DE"})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/usage
# ---------------------------------------------------------------------------


def test_usage_returns_expected_keys(client):
    res = client.get("/api/usage")
    assert res.status_code == 200
    data = res.json()
    assert "local" in data
    assert "deepl" in data
    local = data["local"]
    assert "monthly_total" in local
    assert "monthly_limit" in local
    assert "remaining" in local
    assert "percent_used" in local


# ---------------------------------------------------------------------------
# Bug #5 — DeepL billed_characters from SDK
# ---------------------------------------------------------------------------


def test_translate_uses_billed_characters_from_sdk(client):
    """characters_used in the response must come from result.billed_characters, not len(text)."""
    # Patch the object the router imported — not the module-level singleton which
    # may have been replaced by a module reload in other test classes.
    import app.routers.translate as _translate_router

    with patch.object(
        _translate_router.deepl_service,
        "translate",
        return_value={
            "text": "Übersetzter Text",
            "detected_source": "EN",
            "billed_characters": 42,  # SDK-reported value — intentionally != len(text)
        },
    ):
        res = client.post(
            "/api/translate", json={"text": "Hello world", "target_lang": "DE"}
        )

    assert res.status_code == 200
    data = res.json()
    assert data["characters_used"] == 42, (
        f"Expected characters_used=42 (from SDK billed_characters), got {data['characters_used']}"
    )


def test_write_optimize_sums_billed_characters(client):
    """characters_used for write must be the sum of both SDK billed_characters values."""
    import app.routers.translate as _translate_router

    with patch.object(
        _translate_router.deepl_service,
        "write_optimize",
        return_value={
            "text": "Optimierter Text",
            "detected_lang": "DE",
            "billed_characters": 75,  # billed1 (30) + billed2 (45)
        },
    ):
        res = client.post(
            "/api/write", json={"text": "Some text to optimize", "target_lang": "DE"}
        )

    assert res.status_code == 200
    data = res.json()
    assert data["characters_used"] == 75, (
        f"Expected characters_used=75 (sum of both SDK billed_characters), got {data['characters_used']}"
    )
