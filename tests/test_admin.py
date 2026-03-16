"""Tests for /api/admin/* endpoints and database migrations."""

import pytest

from app.services.user_service import UserService


@pytest.fixture
def admin_client(client):
    """Client logged in as an admin user."""
    svc = UserService()
    svc.create_user(username="admin_user", password="admin123pw", is_admin=True)
    client.post(
        "/api/auth/login",
        json={"username": "admin_user", "password": "admin123pw"},
    )
    return client, svc


@pytest.fixture
def regular_client(client):
    """Client logged in as a regular (non-admin) user."""
    svc = UserService()
    svc.create_user(username="regular_user", password="user123pw")
    client.post(
        "/api/auth/login",
        json={"username": "regular_user", "password": "user123pw"},
    )
    return client, svc


class TestListUsers:
    def test_admin_can_list_users(self, admin_client):
        client, _ = admin_client
        res = client.get("/api/admin/users")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        usernames = [u["username"] for u in res.json()]
        assert "admin_user" in usernames

    def test_admin_user_list_includes_avatar_url(self, admin_client):
        client, _ = admin_client
        res = client.get("/api/admin/users")
        assert res.status_code == 200
        for user in res.json():
            assert "avatar_url" in user
            assert "gravatar.com" in user["avatar_url"]

    def test_regular_user_gets_403(self, regular_client):
        client, _ = regular_client
        res = client.get("/api/admin/users")
        assert res.status_code == 403

    def test_anonymous_gets_401(self, client):
        res = client.get("/api/admin/users")
        assert res.status_code == 401


class TestCreateUser:
    def test_admin_creates_user(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/users",
            json={"username": "newuser", "password": "newpw12345"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["username"] == "newuser"
        assert data["is_admin"] is False
        assert "avatar_url" in data

    def test_admin_creates_user_with_email(self, admin_client):
        import hashlib

        client, _ = admin_client
        email = "gravatar@example.com"
        res = client.post(
            "/api/admin/users",
            json={
                "username": "emaileduser",
                "password": "emailpw12345",
                "email": email,
            },
        )
        assert res.status_code == 201
        data = res.json()
        # gravatar_url() normalizes the email (strip + lowercase) before hashing
        expected_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        assert expected_hash in data["avatar_url"]

    def test_admin_creates_admin_user(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/users",
            json={"username": "newadmin", "password": "adminpw12345", "is_admin": True},
        )
        assert res.status_code == 201
        assert res.json()["is_admin"] is True

    def test_admin_creates_user_with_display_name(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/users",
            json={
                "username": "named_user",
                "password": "namepw12345",
                "display_name": "Named User",
            },
        )
        assert res.status_code == 201
        assert res.json()["display_name"] == "Named User"

    def test_duplicate_username_returns_409(self, admin_client):
        client, _ = admin_client
        client.post(
            "/api/admin/users", json={"username": "dup", "password": "pw12345678"}
        )
        res = client.post(
            "/api/admin/users", json={"username": "dup", "password": "pw12345678"}
        )
        assert res.status_code == 409

    def test_short_username_returns_422(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/users", json={"username": "ab", "password": "pw12345678"}
        )
        assert res.status_code == 422

    def test_short_password_returns_422(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/users", json={"username": "validuser", "password": "short"}
        )
        assert res.status_code == 422

    def test_regular_user_gets_403(self, regular_client):
        client, _ = regular_client
        res = client.post(
            "/api/admin/users",
            json={"username": "attempt", "password": "pw12345678"},
        )
        assert res.status_code == 403


class TestUpdateUser:
    def test_deactivate_user(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="to_deactivate", password="pw12345678")
        res = client.put(f"/api/admin/users/{user.id}", json={"is_active": False})
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    def test_reactivate_user(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="to_reactivate", password="pw12345678")
        svc.update_user(user.id, is_active=False)
        res = client.put(f"/api/admin/users/{user.id}", json={"is_active": True})
        assert res.status_code == 200
        assert res.json()["is_active"] is True

    def test_update_display_name(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="rename_me", password="pw12345678")
        res = client.put(
            f"/api/admin/users/{user.id}", json={"display_name": "New Name"}
        )
        assert res.status_code == 200
        assert res.json()["display_name"] == "New Name"

    def test_cannot_remove_own_admin_rights(self, admin_client):
        client, svc = admin_client
        admin = svc.get_user_by_username("admin_user")
        res = client.put(f"/api/admin/users/{admin.id}", json={"is_admin": False})
        assert res.status_code == 400

    def test_user_not_found_returns_404(self, admin_client):
        client, _ = admin_client
        res = client.put("/api/admin/users/nonexistent-id", json={"is_active": False})
        assert res.status_code == 404


class TestDeleteUser:
    def test_admin_deletes_user(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="to_delete", password="pw12345678")
        res = client.delete(f"/api/admin/users/{user.id}")
        assert res.status_code == 204
        assert svc.get_user_by_id(user.id) is None

    def test_cannot_delete_self(self, admin_client):
        client, svc = admin_client
        admin = svc.get_user_by_username("admin_user")
        res = client.delete(f"/api/admin/users/{admin.id}")
        assert res.status_code == 400

    def test_user_not_found_returns_404(self, admin_client):
        client, _ = admin_client
        res = client.delete("/api/admin/users/nonexistent-id")
        assert res.status_code == 404

    def test_regular_user_gets_403(self, regular_client):
        client, svc = regular_client
        user = svc.create_user(username="some_user", password="pw12345678")
        res = client.delete(f"/api/admin/users/{user.id}")
        assert res.status_code == 403


class TestResetPassword:
    def test_admin_resets_password(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="pw_reset_user", password="oldpw12345")
        res = client.put(
            f"/api/admin/users/{user.id}/password",
            json={"new_password": "newpw12345"},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_new_password_works_for_login(self, admin_client, client):
        adm_client, svc = admin_client
        svc.create_user(username="pw_reset_login", password="oldpw12345")
        user = svc.get_user_by_username("pw_reset_login")
        adm_client.put(
            f"/api/admin/users/{user.id}/password",
            json={"new_password": "newpw12345"},
        )
        res = client.post(
            "/api/auth/login",
            json={"username": "pw_reset_login", "password": "newpw12345"},
        )
        assert res.status_code == 200

    def test_short_password_returns_422(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="short_pw_user", password="pw12345678")
        res = client.put(
            f"/api/admin/users/{user.id}/password",
            json={"new_password": "short"},
        )
        assert res.status_code == 422

    def test_user_not_found_returns_404(self, admin_client):
        client, _ = admin_client
        res = client.put(
            "/api/admin/users/nonexistent/password",
            json={"new_password": "newpw12345"},
        )
        assert res.status_code == 404


class TestUpdateEmail:
    """FINDING-007: Email update via PUT /api/admin/users/{id} was untested."""

    def test_admin_sets_email(self, admin_client):
        import hashlib

        client, svc = admin_client
        email = "user@example.com"
        user = svc.create_user(username="email_target", password="pw12345678")
        res = client.put(
            f"/api/admin/users/{user.id}",
            json={"email": email},
        )
        assert res.status_code == 200
        # gravatar_url() normalizes the email (strip + lowercase) before hashing
        expected_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
        assert expected_hash in res.json()["avatar_url"]

    def test_invalid_email_returns_422(self, admin_client):
        client, svc = admin_client
        user = svc.create_user(username="bad_email_target", password="pw12345678")
        res = client.put(
            f"/api/admin/users/{user.id}",
            json={"email": "not-an-email"},
        )
        assert res.status_code == 422

    def test_email_overwrite_updates_avatar_url(self, admin_client):
        """Updating the email changes the avatar_url to the new email hash."""
        import hashlib

        client, svc = admin_client
        new_email = "new@example.com"
        user = svc.create_user(
            username="email_overwrite", password="pw12345678", email="old@example.com"
        )
        res = client.put(
            f"/api/admin/users/{user.id}",
            json={"email": new_email},
        )
        assert res.status_code == 200
        # gravatar_url() normalizes the email (strip + lowercase) before hashing
        expected_hash = hashlib.md5(new_email.strip().lower().encode()).hexdigest()
        assert expected_hash in res.json()["avatar_url"]

    def test_email_can_be_set_to_null_via_api(self, admin_client):
        """Email can be set to null (gravatar falls back to identicon placeholder)."""
        import hashlib

        client, svc = admin_client
        old_email = "remove@example.com"
        user = svc.create_user(
            username="null_email_test", password="pw12345678", email=old_email
        )
        res = client.put(
            f"/api/admin/users/{user.id}",
            json={"email": None},
        )
        assert res.status_code == 200
        data = res.json()
        # Old email hash must be gone — avatar_url falls back to identicon (no hash)
        old_hash = hashlib.md5(old_email.strip().lower().encode()).hexdigest()
        assert old_hash not in data["avatar_url"]
        assert "identicon" in data["avatar_url"]


class TestMigrateDb:
    """FINDING-006: migrate_db() had no tests — especially for exception handling.

    All tests patch ``app.db.database.engine`` so they run against a controlled
    mock instead of either the production DB or the shared in-memory test DB
    (which lacks the legacy tables that migrate_db() deletes from).
    """

    def _make_mock_engine(self, execute_side_effects):
        """Return a mock engine whose connect() yields a mock connection."""
        from unittest.mock import MagicMock

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        mock_conn.execute.side_effect = execute_side_effects
        return mock_engine, mock_conn

    def test_migrate_db_runs_idempotently(self):
        """Calling migrate_db() twice must not raise.

        Migration steps: DELETE×2 + ADD COLUMN + CREATE INDEX per run.
        Second run: DELETEs are no-ops, ADD COLUMN gets 'duplicate column name',
        CREATE INDEX gets 'already exists' — all silenced.
        """
        from unittest.mock import MagicMock, patch

        from app.db.database import migrate_db

        mock_engine, _ = self._make_mock_engine(
            [MagicMock()] * 20  # more than enough successful responses for two runs
        )
        with patch("app.db.database.engine", mock_engine):
            migrate_db()
            migrate_db()  # second call must not raise

    def test_migrate_db_swallows_duplicate_column_error(self):
        """'duplicate column name' from ADD COLUMN is expected and must be silenced."""
        from unittest.mock import MagicMock, patch

        from sqlalchemy.exc import OperationalError

        from app.db.database import migrate_db

        # DELETE×2 succeed, ADD COLUMN users.email → duplicate, CREATE INDEX succeeds,
        # ADD COLUMN user_settings.ui_language succeeds,
        # Plus 3 token column migrations (word_count, input_tokens, output_tokens) → succeed
        dup_exc = OperationalError("duplicate column name: email", None, Exception())
        mock_engine, _ = self._make_mock_engine(
            [
                MagicMock(),  # DELETE history_records
                MagicMock(),  # DELETE usage_records
                dup_exc,  # ADD COLUMN users.email → duplicate (silenced)
                MagicMock(),  # CREATE UNIQUE INDEX users.email
                MagicMock(),  # ADD COLUMN user_settings.ui_language
                MagicMock(),  # ADD COLUMN usage_records.word_count
                MagicMock(),  # ADD COLUMN usage_records.input_tokens
                MagicMock(),  # ADD COLUMN usage_records.output_tokens
            ]
        )
        with patch("app.db.database.engine", mock_engine):
            migrate_db()  # Must NOT raise

    def test_migrate_db_swallows_cannot_add_unique_column_error(self):
        """'Cannot add a UNIQUE column' from a previous migration attempt is silenced."""
        from unittest.mock import MagicMock, patch

        from sqlalchemy.exc import OperationalError

        from app.db.database import migrate_db

        # Simulates old production DBs where the first migration tried UNIQUE inline
        # DELETE×2 succeed, ADD COLUMN users.email → unique error, CREATE INDEX succeeds,
        # ADD COLUMN user_settings.ui_language succeeds,
        # Plus 3 token column migrations (word_count, input_tokens, output_tokens) → succeed
        unique_exc = OperationalError("Cannot add a UNIQUE column", None, Exception())
        mock_engine, _ = self._make_mock_engine(
            [
                MagicMock(),  # DELETE history_records
                MagicMock(),  # DELETE usage_records
                unique_exc,  # ADD COLUMN users.email → unique error (silenced)
                MagicMock(),  # CREATE UNIQUE INDEX users.email
                MagicMock(),  # ADD COLUMN user_settings.ui_language
                MagicMock(),  # ADD COLUMN usage_records.word_count
                MagicMock(),  # ADD COLUMN usage_records.input_tokens
                MagicMock(),  # ADD COLUMN usage_records.output_tokens
            ]
        )
        with patch("app.db.database.engine", mock_engine):
            migrate_db()  # Must NOT raise

    def test_migrate_db_reraises_unexpected_exceptions(self):
        """Unexpected OperationalErrors from ALTER TABLE must propagate."""
        from unittest.mock import MagicMock, patch

        from sqlalchemy.exc import OperationalError

        from app.db.database import migrate_db

        unexpected_exc = OperationalError("disk I/O error", None, Exception())
        # DELETE×2 succeed, ADD COLUMN raises unexpected error
        mock_engine, _ = self._make_mock_engine(
            [MagicMock(), MagicMock(), unexpected_exc]
        )
        with patch("app.db.database.engine", mock_engine):
            with pytest.raises(OperationalError):
                migrate_db()


class TestDebugLlm:
    def test_non_admin_gets_401(self, client):
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 401

    def test_regular_user_gets_403(self, regular_client):
        client, _ = regular_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 403

    def test_admin_gets_503_when_llm_not_configured(self, admin_client):
        """LLM ist in Tests nicht konfiguriert — 503 erwartet."""
        client, _ = admin_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "translate", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 503

    def test_admin_gets_debug_response_with_mocked_llm(self, admin_client):
        from unittest.mock import AsyncMock, patch

        client, _ = admin_client
        with (
            patch("app.routers.admin.llm_service.is_configured", return_value=True),
            patch(
                "app.routers.admin.llm_service.debug_call", new_callable=AsyncMock
            ) as mock_debug,
        ):
            mock_debug.return_value = {
                "mode": "translate",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompt": "You are a translator...",
                "user_content": "Hello world",
                "raw_response": "Hallo Welt",
                "processed_response": "Hallo Welt",
                "strip_markdown_changed": False,
                "detected_source_lang": "EN",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
            res = client.post(
                "/api/admin/debug/llm",
                json={"mode": "translate", "text": "Hello world", "target_lang": "DE"},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "translate"
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"
        assert data["detected_source_lang"] == "EN"
        assert "system_prompt" in data
        assert "raw_response" in data
        assert "processed_response" in data
        assert "strip_markdown_changed" in data
        assert "usage" in data

    def test_invalid_mode_returns_422(self, admin_client):
        client, _ = admin_client
        res = client.post(
            "/api/admin/debug/llm",
            json={"mode": "invalid", "text": "Hello", "target_lang": "DE"},
        )
        assert res.status_code == 422
