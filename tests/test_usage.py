"""Unit tests for UsageService.

Uses the in-memory SQLite database configured in conftest.py.
"""

from unittest.mock import patch

import pytest

from app.services.usage_service import UsageService


@pytest.fixture
def svc():
    """Fresh UsageService instance per test."""
    return UsageService()


def test_initialization(svc):
    assert svc.monthly_limit > 0


def test_get_usage_stats_returns_expected_keys(svc):
    stats = svc.get_usage_stats("test_user")
    required_keys = {
        "daily_translate",
        "daily_write",
        "daily_total",
        "monthly_translate",
        "monthly_write",
        "monthly_total",
        "monthly_limit",
        "remaining",
        "percent_used",
    }
    assert required_keys.issubset(stats.keys())


def test_initial_usage_is_zero(svc):
    stats = svc.get_usage_stats("new_user_xyz")
    assert stats["monthly_total"] == 0
    assert stats["daily_total"] == 0
    assert stats["remaining"] == svc.monthly_limit


def test_record_translate_usage(svc):
    svc.record_usage(
        "user_a", characters=100, operation_type="translate", target_language="DE"
    )
    stats = svc.get_usage_stats("user_a")
    assert stats["monthly_translate"] == 100
    assert stats["monthly_total"] == 100


def test_record_write_usage(svc):
    svc.record_usage(
        "user_b", characters=200, operation_type="write", target_language="DE"
    )
    stats = svc.get_usage_stats("user_b")
    assert stats["monthly_write"] == 200
    assert stats["monthly_total"] == 200


def test_monthly_total_accumulates(svc):
    uid = "user_acc"
    svc.record_usage(uid, 50, "translate", "DE")
    svc.record_usage(uid, 150, "translate", "EN-GB")
    svc.record_usage(uid, 300, "write", "DE")
    stats = svc.get_usage_stats(uid)
    assert stats["monthly_translate"] == 200
    assert stats["monthly_write"] == 300
    assert stats["monthly_total"] == 500


def test_remaining_decreases_with_usage(svc):
    uid = "user_rem"
    svc.record_usage(uid, 1000, "translate", "DE")
    stats = svc.get_usage_stats(uid)
    assert stats["remaining"] == svc.monthly_limit - 1000


def test_percent_used_is_correct(svc):
    uid = "user_pct"
    half = svc.monthly_limit // 2
    svc.record_usage(uid, half, "translate", "DE")
    stats = svc.get_usage_stats(uid)
    assert abs(stats["percent_used"] - 50.0) < 0.1


def test_daily_total_included_in_monthly(svc):
    uid = "user_daily"
    svc.record_usage(uid, 77, "translate", "DE")
    stats = svc.get_usage_stats(uid)
    # Daily total must be <= monthly total
    assert stats["daily_total"] <= stats["monthly_total"]


def test_record_usage_does_not_raise_on_db_error(svc):
    """record_usage must never propagate an exception (DB failures are logged silently)."""
    with patch("app.services.usage_service.SessionLocal") as mock_session_cls:
        mock_session = mock_session_cls.return_value.__enter__.return_value
        mock_session.execute.side_effect = Exception("Database connection failed")
        # Should not raise
        svc.record_usage("user_err", 100, "translate", "DE")


def test_usage_summary_returns_structure(client):
    """GET /api/usage/summary returns expected shape including llm block."""
    response = client.get("/api/usage/summary")
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "translate" in data
    assert "write" in data
    assert "llm" in data
    assert "words" in data["translate"]
    assert "characters" in data["translate"]
    assert "words" in data["write"]
    # llm block is always present (never None) — Bug C fix
    assert data["llm"] is not None
    assert "input_tokens" in data["llm"]
    assert "output_tokens" in data["llm"]
    assert "configured" in data["llm"]


def test_usage_summary_default_zeros(client):
    """Empty database returns zeros."""
    response = client.get("/api/usage/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["translate"]["words"] == 0
    assert data["write"]["words"] == 0


def test_usage_summary_llm_block_always_present(client):
    """llm-Block muss immer im Response vorhanden und ein Dict sein — auch wenn LLM nicht konfiguriert.

    Bug C: Vorher wurde llm=null zurückgegeben wenn llm_service.is_configured() False war.
    Das verhinderte die 4-Wochen-Token-Summe im Header, selbst wenn Tokens in der DB lagen.
    """
    with patch("app.routers.usage.llm_service") as mock_llm:
        mock_llm.is_configured.return_value = False
        response = client.get("/api/usage/summary")
    assert response.status_code == 200
    data = response.json()
    assert "llm" in data, "llm-Schlüssel fehlt im Response"
    assert data["llm"] is not None, "llm-Wert ist None — sollte immer ein Dict sein"
    assert "input_tokens" in data["llm"]
    assert "output_tokens" in data["llm"]


def test_usage_summary_llm_block_present_when_configured(client):
    """llm-Block muss auch bei konfiguriertem LLM vorhanden sein."""
    with patch("app.routers.usage.llm_service") as mock_llm:
        mock_llm.is_configured.return_value = True
        response = client.get("/api/usage/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["llm"] is not None
    assert "input_tokens" in data["llm"]
    assert "output_tokens" in data["llm"]
