"""Tests for /api/profile endpoints."""

import hashlib

import pytest

from app.services.user_service import UserService
from app.utils import gravatar_url


@pytest.fixture
def logged_in_client(client):
    """Client with an active session for 'profiletest' user."""
    svc = UserService()
    svc.create_user(username="profiletest", password="password123")
    client.post(
        "/api/auth/login",
        json={"username": "profiletest", "password": "password123"},
    )
    return client


class TestGetProfile:
    def test_returns_profile_when_logged_in(self, logged_in_client):
        res = logged_in_client.get("/api/profile")
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "profiletest"
        assert "settings" in data
        assert data["settings"]["theme"] == "light-blue"
        assert data["is_admin"] is False

    def test_returns_401_without_session(self, client):
        res = client.get("/api/profile")
        assert res.status_code == 401

    def test_profile_includes_all_settings_fields(self, logged_in_client):
        data = logged_in_client.get("/api/profile").json()
        settings = data["settings"]
        assert "theme" in settings
        assert "accent_color" in settings
        assert "source_lang" in settings
        assert "target_lang" in settings
        assert "engine_translate" in settings
        assert "engine_write" in settings
        assert "diff_view" in settings

    def test_profile_includes_avatar_url(self, logged_in_client):
        data = logged_in_client.get("/api/profile").json()
        assert "avatar_url" in data
        assert "gravatar.com" in data["avatar_url"]

    def test_avatar_url_is_identicon_without_email(self, logged_in_client):
        """User without email gets identicon fallback."""
        data = logged_in_client.get("/api/profile").json()
        assert "d=identicon" in data["avatar_url"]

    def test_avatar_url_contains_md5_hash_with_email(self, client):
        """User with email gets MD5-hashed Gravatar URL."""
        svc = UserService()
        svc.create_user(
            username="emailuser", password="password123", email="test@example.com"
        )
        client.post(
            "/api/auth/login",
            json={"username": "emailuser", "password": "password123"},
        )
        data = client.get("/api/profile").json()
        expected_hash = hashlib.md5(b"test@example.com").hexdigest()
        assert expected_hash in data["avatar_url"]
        assert "d=identicon" in data["avatar_url"]


class TestGravatarUrl:
    def test_gravatar_url_with_email(self):
        url = gravatar_url("test@example.com")
        assert "gravatar.com/avatar/" in url
        assert "d=identicon" in url

    def test_gravatar_url_without_email(self):
        url = gravatar_url(None)
        assert "d=identicon" in url
        assert "gravatar.com" in url

    def test_gravatar_url_normalises_email_case(self):
        url_lower = gravatar_url("Test@Example.COM")
        expected_hash = hashlib.md5(b"test@example.com").hexdigest()
        assert expected_hash in url_lower

    def test_gravatar_url_custom_size(self):
        url = gravatar_url("a@b.com", size=80)
        assert "s=80" in url

    def test_gravatar_url_default_size(self):
        url = gravatar_url(None)
        assert "s=40" in url


class TestUpdateSettings:
    def test_update_theme(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/settings", json={"theme": "dark-violet"}
        )
        assert res.status_code == 200
        assert res.json()["theme"] == "dark-violet"

    def test_update_diff_view(self, logged_in_client):
        res = logged_in_client.put("/api/profile/settings", json={"diff_view": True})
        assert res.status_code == 200
        assert res.json()["diff_view"] is True

    def test_update_engine_translate(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/settings", json={"engine_translate": "llm"}
        )
        assert res.status_code == 200
        assert res.json()["engine_translate"] == "llm"

    def test_update_accent_color(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/settings", json={"accent_color": "#ff5500"}
        )
        assert res.status_code == 200
        assert res.json()["accent_color"] == "#ff5500"

    def test_reset_accent_color_with_empty_string(self, logged_in_client):
        # Set first
        logged_in_client.put("/api/profile/settings", json={"accent_color": "#ff5500"})
        # Reset with empty string
        res = logged_in_client.put("/api/profile/settings", json={"accent_color": ""})
        assert res.status_code == 200
        assert res.json()["accent_color"] is None

    def test_partial_update_preserves_other_fields(self, logged_in_client):
        # Set theme
        logged_in_client.put("/api/profile/settings", json={"theme": "dark-blue"})
        # Update only diff_view
        res = logged_in_client.put("/api/profile/settings", json={"diff_view": True})
        assert res.status_code == 200
        assert res.json()["theme"] == "dark-blue"  # Preserved
        assert res.json()["diff_view"] is True

    def test_invalid_theme_returns_422(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/settings", json={"theme": "invalid-theme"}
        )
        assert res.status_code == 422

    def test_invalid_engine_returns_422(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/settings", json={"engine_translate": "unknown"}
        )
        assert res.status_code == 422

    def test_returns_401_without_session(self, client):
        res = client.put("/api/profile/settings", json={"theme": "dark-blue"})
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/password",
            json={"current_password": "password123", "new_password": "newpassword456"},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_changed_password_works_for_new_login(self, logged_in_client, client):
        logged_in_client.put(
            "/api/profile/password",
            json={"current_password": "password123", "new_password": "newpassword456"},
        )
        # Old password should fail
        res_old = client.post(
            "/api/auth/login",
            json={"username": "profiletest", "password": "password123"},
        )
        assert res_old.status_code == 401
        # New password should work
        res_new = client.post(
            "/api/auth/login",
            json={"username": "profiletest", "password": "newpassword456"},
        )
        assert res_new.status_code == 200

    def test_wrong_current_password_returns_401(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/password",
            json={
                "current_password": "wrongpassword",
                "new_password": "newpassword456",
            },
        )
        assert res.status_code == 401

    def test_new_password_too_short_returns_422(self, logged_in_client):
        res = logged_in_client.put(
            "/api/profile/password",
            json={"current_password": "password123", "new_password": "short"},
        )
        assert res.status_code == 422

    def test_returns_401_without_session(self, client):
        res = client.put(
            "/api/profile/password",
            json={"current_password": "password123", "new_password": "newpassword456"},
        )
        assert res.status_code == 401
