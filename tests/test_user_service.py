"""Tests for UserService — CRUD, sessions, settings, password hashing."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.user_service import UserService


@pytest.fixture
def svc():
    """Fresh UserService instance per test (stateless service, DB is cleaned by conftest)."""
    return UserService()


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


class TestCreateUser:
    def test_creates_user_with_bcrypt_hash(self, svc):
        user = svc.create_user(username="alice", password="secret123")
        assert user.username == "alice"
        assert user.password_hash is not None
        assert user.password_hash.startswith("$2b$")
        assert user.is_admin is False
        assert user.auth_provider == "local"
        assert user.is_active is True

    def test_creates_default_settings(self, svc):
        user = svc.create_user(username="bob", password="pw12345678")
        settings = svc.get_settings(user.id)
        assert settings is not None
        assert settings.theme == "light-blue"
        assert settings.target_lang == "DE"
        assert settings.diff_view is False

    def test_duplicate_username_raises_value_error(self, svc):
        svc.create_user(username="alice2", password="pw12345678")
        with pytest.raises(ValueError, match="already exists"):
            svc.create_user(username="alice2", password="other123456")

    def test_oidc_user_has_no_password_hash(self, svc):
        user = svc.create_user(
            username="oidc_user",
            auth_provider="oidc",
            oidc_subject="sub|12345",
        )
        assert user.password_hash is None
        assert user.oidc_subject == "sub|12345"
        assert user.auth_provider == "oidc"

    def test_admin_flag_is_set(self, svc):
        user = svc.create_user(
            username="adminuser", password="admin12345", is_admin=True
        )
        assert user.is_admin is True


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------


class TestPasswordVerification:
    def test_correct_password_returns_true(self, svc):
        user = svc.create_user(username="verify1", password="correct_pw!")
        assert svc.verify_password("correct_pw!", user.password_hash) is True

    def test_wrong_password_returns_false(self, svc):
        user = svc.create_user(username="verify2", password="real_pw!")
        assert svc.verify_password("wrong_pw!", user.password_hash) is False

    def test_invalid_hash_returns_false(self, svc):
        assert svc.verify_password("any", "not_a_valid_hash") is False


# ---------------------------------------------------------------------------
# get_user_by_* lookups
# ---------------------------------------------------------------------------


class TestUserLookups:
    def test_get_by_username_found(self, svc):
        svc.create_user(username="lookup_user", password="pw12345678")
        user = svc.get_user_by_username("lookup_user")
        assert user is not None
        assert user.username == "lookup_user"

    def test_get_by_username_not_found(self, svc):
        assert svc.get_user_by_username("nonexistent") is None

    def test_get_by_id(self, svc):
        user = svc.create_user(username="by_id_user", password="pw12345678")
        found = svc.get_user_by_id(user.id)
        assert found is not None
        assert found.id == user.id

    def test_get_by_oidc_subject(self, svc):
        svc.create_user(username="oidc2", auth_provider="oidc", oidc_subject="sub|999")
        user = svc.get_user_by_oidc_subject("sub|999")
        assert user is not None
        assert user.username == "oidc2"

    def test_list_users(self, svc):
        svc.create_user(username="list_a", password="pw12345678")
        svc.create_user(username="list_b", password="pw12345678")
        users = svc.list_users()
        usernames = [u.username for u in users]
        assert "list_a" in usernames
        assert "list_b" in usernames


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_create_and_get_session(self, svc):
        user = svc.create_user(username="sess_user", password="pw1234567")
        session = svc.create_session(user.id)
        assert session.id is not None
        result = svc.get_session(session.id)
        assert result is not None
        _, returned_user = result
        assert returned_user.id == user.id

    def test_expired_session_returns_none(self, svc):
        user = svc.create_user(username="expiry_user", password="pw1234567")
        session = svc.create_session(user.id)
        # Manually expire the session in DB
        from app.db.database import SessionLocal
        from app.db.models import Session as SessionModel

        with SessionLocal() as db:
            s = db.query(SessionModel).filter(SessionModel.id == session.id).first()
            s.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
        assert svc.get_session(session.id) is None

    def test_inactive_user_session_returns_none(self, svc):
        user = svc.create_user(username="inactive_sess", password="pw1234567")
        session = svc.create_session(user.id)
        svc.update_user(user.id, is_active=False)
        assert svc.get_session(session.id) is None

    def test_deactivating_user_deletes_sessions(self, svc):
        from app.db.database import SessionLocal
        from app.db.models import Session as SessionModel

        user = svc.create_user(username="deact_user", password="pw1234567")
        svc.create_session(user.id)
        svc.create_session(user.id)
        svc.update_user(user.id, is_active=False)
        with SessionLocal() as db:
            count = (
                db.query(SessionModel).filter(SessionModel.user_id == user.id).count()
            )
        assert count == 0

    def test_delete_session(self, svc):
        user = svc.create_user(username="del_sess_user", password="pw1234567")
        session = svc.create_session(user.id)
        svc.delete_session(session.id)
        assert svc.get_session(session.id) is None

    def test_delete_nonexistent_session_is_noop(self, svc):
        # Should not raise
        svc.delete_session("nonexistent-id")

    def test_remember_me_creates_longer_session(self, svc):
        user = svc.create_user(username="remember_user", password="pw1234567")
        normal = svc.create_session(user.id, remember_me=False)
        remember = svc.create_session(user.id, remember_me=True)
        assert remember.expires_at > normal.expires_at

    def test_cleanup_expired_sessions(self, svc):
        from app.db.database import SessionLocal
        from app.db.models import Session as SessionModel

        user = svc.create_user(username="cleanup_user", password="pw1234567")
        session = svc.create_session(user.id)
        # Expire it
        with SessionLocal() as db:
            s = db.query(SessionModel).filter(SessionModel.id == session.id).first()
            s.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
        count = svc.cleanup_expired_sessions()
        assert count >= 1


# ---------------------------------------------------------------------------
# User update + delete
# ---------------------------------------------------------------------------


class TestUpdateAndDelete:
    def test_update_display_name(self, svc):
        user = svc.create_user(username="update_dn", password="pw12345678")
        updated = svc.update_user(user.id, display_name="Alice Updated")
        assert updated.display_name == "Alice Updated"

    def test_update_is_admin(self, svc):
        user = svc.create_user(username="make_admin", password="pw12345678")
        updated = svc.update_user(user.id, is_admin=True)
        assert updated.is_admin is True

    def test_update_nonexistent_returns_none(self, svc):
        assert svc.update_user("nonexistent-id", is_active=False) is None

    def test_delete_removes_user(self, svc):
        user = svc.create_user(username="del_user", password="pw12345678")
        user_id = user.id
        assert svc.delete_user(user_id) is True
        assert svc.get_user_by_id(user_id) is None

    def test_delete_removes_settings(self, svc):
        user = svc.create_user(username="del_settings", password="pw12345678")
        user_id = user.id
        svc.delete_user(user_id)
        assert svc.get_settings(user_id) is None

    def test_delete_nonexistent_returns_false(self, svc):
        assert svc.delete_user("nonexistent-id") is False

    def test_set_password(self, svc):
        user = svc.create_user(username="pw_change", password="oldpassword")
        svc.set_password(user.id, "newpassword123")
        updated = svc.get_user_by_id(user.id)
        assert svc.verify_password("newpassword123", updated.password_hash) is True
        assert svc.verify_password("oldpassword", updated.password_hash) is False


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------


class TestUserSettings:
    def test_partial_update_theme(self, svc):
        user = svc.create_user(username="settings_user", password="pw12345678")
        result = svc.update_settings(user.id, theme="dark-violet")
        assert result.theme == "dark-violet"
        # Unchanged fields retain defaults
        assert result.target_lang == "DE"

    def test_partial_update_diff_view(self, svc):
        user = svc.create_user(username="settings_user2", password="pw12345678")
        result = svc.update_settings(user.id, diff_view=True)
        assert result.diff_view is True

    def test_update_nonexistent_returns_none(self, svc):
        assert svc.update_settings("fake-id", theme="dark-blue") is None


# ---------------------------------------------------------------------------
# OIDC provisioning
# ---------------------------------------------------------------------------


class TestOidcProvisioning:
    def test_first_login_creates_user(self, svc):
        user = svc.provision_oidc_user(subject="sub|oidc001", username="oidcuser")
        assert user.username == "oidcuser"
        assert user.oidc_subject == "sub|oidc001"
        assert user.auth_provider == "oidc"

    def test_second_login_returns_existing_user(self, svc):
        user1 = svc.provision_oidc_user(subject="sub|oidc002", username="oidcuser2")
        user2 = svc.provision_oidc_user(subject="sub|oidc002", username="oidcuser2")
        assert user1.id == user2.id

    def test_username_conflict_gets_suffix(self, svc):
        svc.create_user(username="taken", password="pw12345678")
        user = svc.provision_oidc_user(subject="sub|conflict", username="taken")
        assert user.username == "taken_1"


# ---------------------------------------------------------------------------
# Admin bootstrap
# ---------------------------------------------------------------------------


class TestAdminBootstrap:
    def test_ensure_admin_creates_user_when_no_users(self, svc, monkeypatch):
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        mock_settings = MagicMock()
        mock_settings.admin_username = "bootstrap_admin"
        mock_settings.admin_password = SecretStr("bootstrap_pw123")
        mock_settings.session_lifetime_hours = 24
        mock_settings.session_lifetime_remember_hours = 720

        import app.services.user_service as us_module

        monkeypatch.setattr(us_module, "settings", mock_settings)

        svc2 = UserService()
        svc2.ensure_admin_user()
        user = svc2.get_user_by_username("bootstrap_admin")
        assert user is not None
        assert user.is_admin is True

    def test_ensure_admin_skips_when_users_exist(self, svc, monkeypatch):
        svc.create_user(username="existing", password="pw12345678")
        from unittest.mock import MagicMock

        from pydantic import SecretStr

        mock_settings = MagicMock()
        mock_settings.admin_username = "new_admin"
        mock_settings.admin_password = SecretStr("newadmin123")
        mock_settings.session_lifetime_hours = 24
        mock_settings.session_lifetime_remember_hours = 720

        import app.services.user_service as us_module

        monkeypatch.setattr(us_module, "settings", mock_settings)

        svc2 = UserService()
        svc2.ensure_admin_user()
        # new_admin should NOT have been created
        assert svc2.get_user_by_username("new_admin") is None
