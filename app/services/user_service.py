"""User and session management service."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Session, User, UserSettings

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Sentinel: distinguish "email not provided" from "email explicitly set to None"
_UNSET = object()


class UserService:
    """CRUD and session management for User, Session, UserSettings."""

    # ------------------------------------------------------------------
    # Password hashing
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plaintext password using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a plaintext password against a bcrypt hash."""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: Optional[str] = None,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        is_admin: bool = False,
        auth_provider: str = "local",
        oidc_subject: Optional[str] = None,
    ) -> User:
        """Create a new user and default settings. Raises ValueError if username exists."""
        with SessionLocal() as db:
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                raise ValueError(f"Username already exists: {username}")
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=self.hash_password(password) if password else None,
                display_name=display_name,
                email=email,
                is_admin=is_admin,
                auth_provider=auth_provider,
                oidc_subject=oidc_subject,
            )
            db.add(user)
            # Create default settings row for new user
            settings_obj = UserSettings(user_id=user.id, ui_language="en")
            db.add(settings_obj)
            db.commit()
            db.refresh(user)
            logger.info("User created: %s (admin=%s)", username, is_admin)
            return user

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        with SessionLocal() as db:
            return db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        with SessionLocal() as db:
            return db.query(User).filter(User.username == username).first()

    def get_user_by_oidc_subject(self, subject: str) -> Optional[User]:
        with SessionLocal() as db:
            return db.query(User).filter(User.oidc_subject == subject).first()

    def list_users(self) -> list[User]:
        with SessionLocal() as db:
            return db.query(User).order_by(User.created_at).all()

    def update_user(
        self,
        user_id: str,
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None,
        display_name: Optional[str] = None,
        email=_UNSET,
    ) -> Optional[User]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            if is_active is not None:
                user.is_active = is_active
                if not is_active:
                    # Invalidate all sessions when deactivating user
                    db.query(Session).filter(Session.user_id == user_id).delete()
            if is_admin is not None:
                user.is_admin = is_admin
            if display_name is not None:
                user.display_name = display_name
            if email is not _UNSET:
                # Allows clearing email to None (sentinel distinguishes "not provided" from None)
                user.email = email
            user.updated_at = _now_utc()
            db.commit()
            db.refresh(user)
            return user

    def delete_user(self, user_id: str) -> bool:
        """Delete user and all associated data (sessions, settings, history, usage)."""
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            # Explicitly delete all associated records before deleting the user.
            # This ensures cascade works even when SQLite foreign_keys PRAGMA is off
            # (which is the case in the in-memory test database).
            from app.db.models import HistoryRecord, UsageRecord

            db.query(Session).filter(Session.user_id == user_id).delete()
            db.query(UserSettings).filter(UserSettings.user_id == user_id).delete()
            db.query(HistoryRecord).filter(HistoryRecord.user_id == user_id).delete()
            db.query(UsageRecord).filter(UsageRecord.user_id == user_id).delete()
            db.delete(user)
            db.commit()
            logger.info("User deleted: %s", user_id)
            return True

    def set_password(self, user_id: str, new_password: str) -> bool:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            user.password_hash = self.hash_password(new_password)
            user.updated_at = _now_utc()
            db.commit()
            return True

    def update_last_login(self, user_id: str) -> None:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.last_login_at = _now_utc()
                db.commit()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        remember_me: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Session:
        lifetime_hours = (
            settings.session_lifetime_remember_hours
            if remember_me
            else settings.session_lifetime_hours
        )
        expires_at = _now_utc() + timedelta(hours=lifetime_hours)
        with SessionLocal() as db:
            session = Session(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    def get_session(self, session_id: str) -> Optional[tuple[Session, User]]:
        """Return (session, user) if session is valid and not expired. None otherwise."""
        with SessionLocal() as db:
            session = db.query(Session).filter(Session.id == session_id).first()
            if not session:
                return None
            # Normalise timezone for comparison
            expires = session.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < _now_utc():
                db.delete(session)
                db.commit()
                return None
            user = db.query(User).filter(User.id == session.user_id).first()
            if not user or not user.is_active:
                return None
            return session, user

    def delete_session(self, session_id: str) -> None:
        with SessionLocal() as db:
            session = db.query(Session).filter(Session.id == session_id).first()
            if session:
                db.delete(session)
                db.commit()

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions. Returns count of deleted sessions."""
        with SessionLocal() as db:
            count = db.query(Session).filter(Session.expires_at < _now_utc()).delete()
            db.commit()
            return count

    # ------------------------------------------------------------------
    # User settings
    # ------------------------------------------------------------------

    def get_settings(self, user_id: str) -> Optional[UserSettings]:
        with SessionLocal() as db:
            return (
                db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            )

    def update_settings(self, user_id: str, **kwargs) -> Optional[UserSettings]:
        """Partial update — only provided kwargs are written."""
        with SessionLocal() as db:
            s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not s:
                return None
            for key, value in kwargs.items():
                if hasattr(s, key):
                    setattr(s, key, value)
            s.updated_at = _now_utc()
            db.commit()
            db.refresh(s)
            return s

    # ------------------------------------------------------------------
    # OIDC auto-provisioning
    # ------------------------------------------------------------------

    def provision_oidc_user(self, subject: str, username: str) -> User:
        """Get existing OIDC user by subject, or create a new one."""
        existing = self.get_user_by_oidc_subject(subject)
        if existing:
            return existing
        # Ensure unique username (append numeric suffix if taken)
        base = username
        attempt = username
        counter = 1
        while self.get_user_by_username(attempt):
            attempt = f"{base}_{counter}"
            counter += 1
        return self.create_user(
            username=attempt,
            auth_provider="oidc",
            oidc_subject=subject,
        )

    # ------------------------------------------------------------------
    # Admin bootstrap
    # ------------------------------------------------------------------

    def ensure_admin_user(self) -> None:
        """Create the initial admin user from ADMIN_USERNAME / ADMIN_PASSWORD env vars.

        Only runs if no users exist yet and both env vars are set.
        Safe to call multiple times (idempotent).
        """
        if not settings.admin_username or not settings.admin_password:
            return
        with SessionLocal() as db:
            count = db.query(User).count()
        if count > 0:
            return
        try:
            self.create_user(
                username=settings.admin_username,
                password=settings.admin_password.get_secret_value(),
                is_admin=True,
            )
            logger.info("Initial admin user created: %s", settings.admin_username)
        except ValueError:
            pass  # Username already exists — race condition guard


user_service = UserService()
