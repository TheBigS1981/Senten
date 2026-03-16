"""Tests for /api/auth/login and /api/auth/logout endpoints."""

import pytest

from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def test_user():
    """Create a standard test user before each test."""
    svc = UserService()
    svc.create_user(username="logintest", password="password123")
    yield


class TestLogin:
    def test_valid_login_returns_ok_and_sets_cookie(self, client):
        res = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "password123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["username"] == "logintest"
        assert data["is_admin"] is False
        assert "senten_session" in res.cookies

    def test_wrong_password_returns_401(self, client):
        res = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "wrongpassword"},
        )
        assert res.status_code == 401
        assert "senten_session" not in res.cookies

    def test_unknown_user_returns_401(self, client):
        res = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "pw12345678"},
        )
        assert res.status_code == 401

    def test_inactive_user_cannot_login(self, client):
        svc = UserService()
        user = svc.get_user_by_username("logintest")
        svc.update_user(user.id, is_active=False)
        res = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "password123"},
        )
        assert res.status_code == 401

    def test_empty_password_returns_422(self, client):
        res = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": ""},
        )
        assert res.status_code == 422

    def test_remember_me_flag_accepted(self, client):
        res = client.post(
            "/api/auth/login",
            json={
                "username": "logintest",
                "password": "password123",
                "remember_me": True,
            },
        )
        assert res.status_code == 200
        assert "senten_session" in res.cookies

    def test_admin_user_returns_is_admin_true(self, client):
        svc = UserService()
        svc.create_user(username="adminlogin", password="adminpw123", is_admin=True)
        res = client.post(
            "/api/auth/login",
            json={"username": "adminlogin", "password": "adminpw123"},
        )
        assert res.status_code == 200
        assert res.json()["is_admin"] is True


class TestLogout:
    def test_logout_deletes_session(self, client):
        # Login first
        login_res = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "password123"},
        )
        assert login_res.status_code == 200
        session_id = login_res.cookies.get("senten_session")
        assert session_id

        # Logout
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200
        assert logout_res.json()["ok"] is True

        # Session should be gone
        svc = UserService()
        assert svc.get_session(session_id) is None

    def test_logout_without_cookie_returns_ok(self, client):
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_session_invalid_after_logout(self, client):
        # Login and get profile
        client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "password123"},
        )
        profile_before = client.get("/api/profile")
        assert profile_before.status_code == 200

        # Logout
        client.post("/api/auth/logout")

        # Profile should now return 401
        profile_after = client.get("/api/profile")
        assert profile_after.status_code == 401
