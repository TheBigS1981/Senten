# Benutzerverwaltung & Profile — Implementierungsplan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Benutzerverwaltung mit Login, serverseitigen Settings, benutzerspezifischem Verlauf und Admin-UI hinzufügen.

**Architecture:** HttpOnly Session-Cookie + serverseitige Session-Tabelle in SQLite. Drei neue DB-Tabellen (`users`, `sessions`, `user_settings`). Bestehende Auth-Middleware wird um Session-Cookie-Validierung erweitert — OIDC und Basic Auth bleiben erhalten. `ALLOW_ANONYMOUS=true` (Default) sichert Abwärtskompatibilität.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, bcrypt, Pydantic v2, Vanilla JS, Jinja2

---

## Übersicht der Tasks

| Task | Beschreibung | Dateien |
|------|-------------|---------|
| 1 | DB-Models: `users`, `sessions`, `user_settings` | `app/db/models.py` |
| 2 | Config: Neue Settings + bcrypt-Dependency | `app/config.py`, `requirements.txt` |
| 3 | Pydantic-Schemas: User, Login, Settings | `app/models/schemas.py` |
| 4 | UserService: CRUD, Session, Passwort-Hashing | `app/services/user_service.py` (neu) |
| 5 | Auth-Router: Login / Logout | `app/routers/auth.py` (ersetzen) |
| 6 | Profile-Router: GET/PUT /api/profile | `app/routers/profile.py` (neu) |
| 7 | Admin-Router: User-CRUD | `app/routers/admin.py` (neu) |
| 8 | Auth-Middleware: Session-Cookie-Validierung | `app/middleware/auth.py` |
| 9 | DB-Migration: Anonyme Records löschen, init-Admin | `app/db/database.py` |
| 10 | main.py: Neue Router registrieren | `app/main.py` |
| 11 | Frontend: Login-Seite | `templates/login.html` (neu) |
| 12 | Frontend: Header (Profil-Button, Admin-Link) | `templates/index.html` |
| 13 | Frontend: Settings via API statt localStorage | `static/js/app.js` |
| 14 | Frontend: Admin-UI | `static/js/admin.js` (neu) |
| 15 | Tests: UserService | `tests/test_user_service.py` (neu) |
| 16 | Tests: Auth-Router (Login/Logout) | `tests/test_auth_router.py` (neu) |
| 17 | Tests: Profile-Router | `tests/test_profile.py` (neu) |
| 18 | Tests: Admin-Router | `tests/test_admin.py` (neu) |
| 19 | Tests: Auth-Middleware (Session-Modus) | `tests/test_auth.py` (erweitern) |
| 20 | .env.example + Docs aktualisieren | `.env.example`, `docs/` |

---

## Task 1: DB-Models

**Files:**
- Modify: `app/db/models.py`

### Was wird gemacht

Drei neue SQLAlchemy-Models: `User`, `Session`, `UserSettings`. Bestehende Models (`UsageRecord`, `HistoryRecord`) behalten ihr `user_id`-Feld als String — FK-Migration kommt in Task 9.

### Step 1: Models erweitern

Füge am Ende von `app/db/models.py` folgende Models hinzu:

```python
import uuid
from sqlalchemy import Boolean, ForeignKey

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)          # null bei OIDC-only
    display_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    auth_provider = Column(String, default="local", nullable=False)  # "local" | "oidc"
    oidc_subject = Column(String, nullable=True, unique=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    __table_args__ = (
        Index("ix_users_username", "username"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme = Column(String, default="light-blue", nullable=False)
    accent_color = Column(String, nullable=True)
    source_lang = Column(String, nullable=True)
    target_lang = Column(String, default="DE", nullable=False)
    engine_translate = Column(String, default="deepl", nullable=False)
    engine_write = Column(String, default="deepl", nullable=False)
    formality = Column(String, default="default", nullable=False)
    diff_view = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)
```

### Step 2: Import-Zeile ergänzen

Ergänze am Anfang der Datei `uuid` und `Boolean`, `ForeignKey`:

```python
import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
```

### Step 3: Teste, dass Import funktioniert

```bash
python3 -c "from app.db.models import User, Session, UserSettings; print('OK')"
```

Erwartet: `OK`

### Step 4: Commit

```bash
git add app/db/models.py
git commit -m "feat(db): add User, Session, UserSettings models"
```

---

## Task 2: Config-Erweiterung + bcrypt-Dependency

**Files:**
- Modify: `app/config.py`
- Modify: `requirements.txt`

### Step 1: `requirements.txt` — bcrypt hinzufügen

Füge nach dem letzten Eintrag (alphabetisch sortiert) hinzu:

```
bcrypt==4.2.1
```

### Step 2: Installation prüfen

```bash
pip install bcrypt==4.2.1
```

### Step 3: `app/config.py` — neue Settings

Ergänze in der `Settings`-Klasse nach `auth_password`:

```python
    # User management
    allow_anonymous: bool = True             # Allow unauthenticated access
    admin_username: Optional[str] = None     # Initial admin username
    admin_password: Optional[SecretStr] = None  # Initial admin password
    session_lifetime_hours: int = Field(default=24, ge=1)          # Session duration
    session_lifetime_remember_hours: int = Field(default=720, ge=1) # "Remember me" duration
```

### Step 4: Teste Import

```bash
python3 -c "from app.config import settings; print(settings.allow_anonymous, settings.session_lifetime_hours)"
```

Erwartet: `True 24`

### Step 5: Commit

```bash
git add app/config.py requirements.txt
git commit -m "feat(config): add user management settings and bcrypt dependency"
```

---

## Task 3: Pydantic-Schemas

**Files:**
- Modify: `app/models/schemas.py`

### Step 1: Schemas hinzufügen

Füge am Ende von `app/models/schemas.py` folgende Schemas hinzu:

```python
# ---------------------------------------------------------------------------
# User management schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)
    remember_me: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class UserSettingsSchema(BaseModel):
    """Partial update allowed — all fields optional."""
    theme: Optional[str] = Field(default=None, pattern=r"^(light|dark)-(blue|violet)$")
    accent_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$|^$")
    source_lang: Optional[str] = Field(default=None, max_length=10)
    target_lang: Optional[str] = Field(default=None, max_length=10)
    engine_translate: Optional[str] = Field(default=None, pattern=r"^(deepl|llm)$")
    engine_write: Optional[str] = Field(default=None, pattern=r"^(deepl|llm)$")
    formality: Optional[str] = Field(default=None, pattern=r"^(default|more|less|prefer_more|prefer_less)$")
    diff_view: Optional[bool] = None

    model_config = ConfigDict(str_strip_whitespace=True)


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    theme: str
    accent_color: Optional[str]
    source_lang: Optional[str]
    target_lang: str
    engine_translate: str
    engine_write: str
    formality: str
    diff_view: bool
    updated_at: datetime


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: Optional[str]
    is_admin: bool
    auth_provider: str
    last_login_at: Optional[datetime]
    settings: UserSettingsResponse


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: Optional[str]
    is_admin: bool
    is_active: bool
    auth_provider: str
    last_login_at: Optional[datetime]
    created_at: datetime


class AdminUserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=200)
    is_admin: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminUserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    display_name: Optional[str] = Field(default=None, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)
```

### Step 2: Import-Check

```bash
python3 -c "from app.models.schemas import LoginRequest, UserProfileResponse, AdminUserCreateRequest; print('OK')"
```

Erwartet: `OK`

### Step 3: Commit

```bash
git add app/models/schemas.py
git commit -m "feat(schemas): add user management Pydantic schemas"
```

---

## Task 4: UserService

**Files:**
- Create: `app/services/user_service.py`

### Was wird gemacht

Zentraler Service für alle User-Operationen: CRUD, Passwort-Hashing (bcrypt), Session-Management. Keine Business-Logik in Routern — alles hier.

### Step 1: Datei erstellen

```python
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
        is_admin: bool = False,
        auth_provider: str = "local",
        oidc_subject: Optional[str] = None,
    ) -> User:
        """Create a new user. Raises ValueError if username already exists."""
        with SessionLocal() as db:
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                raise ValueError(f"Username already exists: {username}")
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=self.hash_password(password) if password else None,
                display_name=display_name,
                is_admin=is_admin,
                auth_provider=auth_provider,
                oidc_subject=oidc_subject,
            )
            db.add(user)
            # Create default settings for new user
            settings_obj = UserSettings(user_id=user.id)
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
    ) -> Optional[User]:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            if is_active is not None:
                user.is_active = is_active
                if not is_active:
                    # Invalidate all sessions when deactivating
                    db.query(Session).filter(Session.user_id == user_id).delete()
            if is_admin is not None:
                user.is_admin = is_admin
            if display_name is not None:
                user.display_name = display_name
            user.updated_at = _now_utc()
            db.commit()
            db.refresh(user)
            return user

    def delete_user(self, user_id: str) -> bool:
        """Delete user and cascade: sessions, settings, history, usage records."""
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            # SQLAlchemy cascade via ForeignKey ondelete="CASCADE" handles sessions + settings
            # History and usage records use user_id string (no FK), delete manually
            from app.db.models import HistoryRecord, UsageRecord
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
            if session.expires_at.replace(tzinfo=timezone.utc) < _now_utc():
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
        """Delete all expired sessions. Returns count deleted."""
        with SessionLocal() as db:
            count = db.query(Session).filter(Session.expires_at < _now_utc()).delete()
            db.commit()
            return count

    # ------------------------------------------------------------------
    # User settings
    # ------------------------------------------------------------------

    def get_settings(self, user_id: str) -> Optional[UserSettings]:
        with SessionLocal() as db:
            return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

    def update_settings(self, user_id: str, **kwargs) -> Optional[UserSettings]:
        """Partial update — only provided kwargs are written."""
        with SessionLocal() as db:
            s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not s:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(s, key):
                    setattr(s, key, value)
            s.updated_at = _now_utc()
            db.commit()
            db.refresh(s)
            return s

    # ------------------------------------------------------------------
    # OIDC auto-provisioning
    # ------------------------------------------------------------------

    def provision_oidc_user(self, subject: str, username: str) -> User:
        """Get existing OIDC user or create a new one."""
        existing = self.get_user_by_oidc_subject(subject)
        if existing:
            return existing
        # Ensure unique username (append suffix if taken)
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

        Only runs if no users exist yet and both vars are set.
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
            pass  # Already exists — race condition guard


user_service = UserService()
```

### Step 2: Import prüfen

```bash
python3 -c "from app.services.user_service import user_service; print('OK')"
```

Erwartet: `OK`

### Step 3: Commit

```bash
git add app/services/user_service.py
git commit -m "feat(services): add UserService with CRUD, session management, bcrypt"
```

---

## Task 5: Auth-Router (Login / Logout)

**Files:**
- Replace: `app/routers/auth.py`

### Kontext

Die bestehende `app/routers/auth.py` enthält nur den `/logout`-Endpunkt. Sie wird durch eine vollständige Version mit Login + Logout ersetzt.

### Step 1: Neuen Auth-Router schreiben

```python
"""Authentication endpoints: Login and Logout."""

import logging

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi import status as http_status

from app.models.schemas import LoginRequest
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_COOKIE_NAME = "senten_session"


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/auth/login", tags=["Auth"])
async def login(body: LoginRequest, request: Request, response: Response):
    """Authenticate with username + password, set HttpOnly session cookie."""
    user = user_service.get_user_by_username(body.username)

    # Constant-time: always verify even if user not found (dummy hash prevents timing attack)
    _DUMMY_HASH = "$2b$12$invalid.hash.for.timing.protection"
    candidate_hash = user.password_hash if (user and user.password_hash) else _DUMMY_HASH
    password_ok = user_service.verify_password(body.password, candidate_hash)

    if not user or not password_ok or not user.is_active:
        logger.warning("Failed login attempt for username: %s", body.username)
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Benutzername oder Passwort falsch.",
        )

    session = user_service.create_session(
        user_id=user.id,
        remember_me=body.remember_me,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    user_service.update_last_login(user.id)

    # Calculate max_age from session expiry
    from datetime import timezone
    from datetime import datetime as dt
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    max_age = int((expires_at - dt.now(timezone.utc)).total_seconds())

    response.set_cookie(
        key=_SESSION_COOKIE_NAME,
        value=session.id,
        max_age=max_age,
        httponly=True,
        secure=False,   # Set True in production behind HTTPS
        samesite="lax",
        path="/",
    )
    logger.info("User logged in: %s", user.username)
    return {"ok": True, "username": user.username, "is_admin": user.is_admin}


@router.post("/auth/logout", tags=["Auth"])
async def logout(
    response: Response,
    senten_session: str = Cookie(default=None),
):
    """Invalidate session cookie and delete server-side session."""
    if senten_session:
        user_service.delete_session(senten_session)
    response.delete_cookie(key=_SESSION_COOKIE_NAME, path="/")
    return {"ok": True}
```

### Step 2: Import prüfen

```bash
python3 -c "from app.routers.auth import router; print('OK')"
```

Erwartet: `OK`

### Step 3: Commit

```bash
git add app/routers/auth.py
git commit -m "feat(auth): add login/logout endpoints with session cookie"
```

---

## Task 6: Profile-Router

**Files:**
- Create: `app/routers/profile.py`

### Step 1: Datei erstellen

```python
"""User profile and settings endpoints."""

import logging

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi import status as http_status

from app.models.schemas import (
    ChangePasswordRequest,
    UserProfileResponse,
    UserSettingsResponse,
    UserSettingsSchema,
)
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_COOKIE_NAME = "senten_session"


def _require_session(senten_session: str | None) -> tuple:
    """Validate session cookie and return (session, user). Raises 401 if invalid."""
    if not senten_session:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    result = user_service.get_session(senten_session)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Session abgelaufen oder ungültig.")
    return result


@router.get("/profile", response_model=UserProfileResponse, tags=["Profile"])
async def get_profile(senten_session: str = Cookie(default=None)):
    """Return current user profile + settings."""
    _, user = _require_session(senten_session)
    settings_obj = user_service.get_settings(user.id)
    if not settings_obj:
        raise HTTPException(status_code=500, detail="Settings nicht gefunden.")
    return UserProfileResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_provider=user.auth_provider,
        last_login_at=user.last_login_at,
        settings=UserSettingsResponse.model_validate(settings_obj),
    )


@router.put("/profile/settings", response_model=UserSettingsResponse, tags=["Profile"])
async def update_settings(
    body: UserSettingsSchema,
    senten_session: str = Cookie(default=None),
):
    """Partial update of user settings."""
    _, user = _require_session(senten_session)
    updates = body.model_dump(exclude_none=True)
    # accent_color: empty string means reset to None
    if "accent_color" in updates and updates["accent_color"] == "":
        updates["accent_color"] = None
    result = user_service.update_settings(user.id, **updates)
    if not result:
        raise HTTPException(status_code=500, detail="Settings konnten nicht gespeichert werden.")
    return UserSettingsResponse.model_validate(result)


@router.put("/profile/password", tags=["Profile"])
async def change_password(
    body: ChangePasswordRequest,
    senten_session: str = Cookie(default=None),
):
    """Change own password (local auth only)."""
    _, user = _require_session(senten_session)
    if user.auth_provider != "local" or not user.password_hash:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Passwort kann nur bei lokaler Authentifizierung geändert werden.",
        )
    if not user_service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Aktuelles Passwort falsch.",
        )
    user_service.set_password(user.id, body.new_password)
    return {"ok": True}
```

### Step 2: Import prüfen

```bash
python3 -c "from app.routers.profile import router; print('OK')"
```

### Step 3: Commit

```bash
git add app/routers/profile.py
git commit -m "feat(profile): add GET /api/profile and PUT /api/profile/settings"
```

---

## Task 7: Admin-Router

**Files:**
- Create: `app/routers/admin.py`

### Step 1: Datei erstellen

```python
"""Admin-only user management endpoints."""

import logging

from fastapi import APIRouter, Cookie, HTTPException
from fastapi import status as http_status

from app.models.schemas import (
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from app.services.user_service import user_service

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_COOKIE_NAME = "senten_session"


def _require_admin(senten_session: str | None):
    """Validate session and require admin rights. Returns user."""
    if not senten_session:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    result = user_service.get_session(senten_session)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Session ungültig.")
    _, user = result
    if not user.is_admin:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Admin-Rechte erforderlich.")
    return user


@router.get("/admin/users", response_model=list[AdminUserResponse], tags=["Admin"])
async def list_users(senten_session: str = Cookie(default=None)):
    """List all users (admin only)."""
    _require_admin(senten_session)
    users = user_service.list_users()
    return [AdminUserResponse.model_validate(u) for u in users]


@router.post("/admin/users", response_model=AdminUserResponse, status_code=201, tags=["Admin"])
async def create_user(
    body: AdminUserCreateRequest,
    senten_session: str = Cookie(default=None),
):
    """Create a new local user (admin only)."""
    _require_admin(senten_session)
    try:
        user = user_service.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            is_admin=body.is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(e))
    return AdminUserResponse.model_validate(user)


@router.put("/admin/users/{user_id}", response_model=AdminUserResponse, tags=["Admin"])
async def update_user(
    user_id: str,
    body: AdminUserUpdateRequest,
    senten_session: str = Cookie(default=None),
):
    """Update user (active, admin, display_name). Admin only."""
    admin = _require_admin(senten_session)
    # Prevent admin from removing their own admin rights
    if user_id == admin.id and body.is_admin is False:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Du kannst dir selbst keine Admin-Rechte entziehen.",
        )
    updates = body.model_dump(exclude_none=True)
    user = user_service.update_user(user_id, **updates)
    if not user:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden.")
    return AdminUserResponse.model_validate(user)


@router.delete("/admin/users/{user_id}", status_code=204, tags=["Admin"])
async def delete_user(
    user_id: str,
    senten_session: str = Cookie(default=None),
):
    """Delete user and all associated data (admin only)."""
    admin = _require_admin(senten_session)
    if user_id == admin.id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Du kannst dich nicht selbst löschen.",
        )
    deleted = user_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden.")


@router.put("/admin/users/{user_id}/password", tags=["Admin"])
async def reset_password(
    user_id: str,
    body: AdminPasswordResetRequest,
    senten_session: str = Cookie(default=None),
):
    """Reset a user's password (admin only)."""
    _require_admin(senten_session)
    ok = user_service.set_password(user_id, body.new_password)
    if not ok:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden.")
    return {"ok": True}
```

### Step 2: Import prüfen

```bash
python3 -c "from app.routers.admin import router; print('OK')"
```

### Step 3: Commit

```bash
git add app/routers/admin.py
git commit -m "feat(admin): add admin user management endpoints"
```

---

## Task 8: Auth-Middleware — Session-Cookie-Validierung

**Files:**
- Modify: `app/middleware/auth.py`

### Was wird gemacht

Die bestehende Middleware behält ihre drei Modi (OIDC, Basic, Anonym). Ein vierter Modus wird **immer zuerst** geprüft: Session-Cookie. Wenn ein gültiges `senten_session`-Cookie vorhanden ist, wird der User aus der Session geladen — unabhängig vom konfigurierten Auth-Modus. Das ermöglicht browser-basierte Logins parallel zu API-Authentifizierung.

Zusätzlich: Wenn `ALLOW_ANONYMOUS=false` und kein Cookie und kein Auth-Header, redirect zu `/login` (für HTML-Requests) oder 401 (für API-Requests).

### Step 1: Imports erweitern

Am Anfang der Datei nach den bestehenden Imports hinzufügen:

```python
from app.config import settings as app_settings  # Alias to avoid shadowing

_SESSION_COOKIE_NAME = "senten_session"
```

> **Achtung:** `settings` ist bereits importiert — nutze denselben Import, ergänze nur `_SESSION_COOKIE_NAME`.

### Step 2: `dispatch`-Methode erweitern

Den bestehenden `dispatch`-Block nach dem Exempt-Check und VOR dem Rate-Limit-Check um Session-Cookie-Validierung erweitern:

```python
async def dispatch(self, request: Request, call_next) -> Response:
    path = request.url.path
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        request.state.user_id = "anonymous"
        request.state.user = None
        return await call_next(request)

    # --- Session cookie check (runs for all modes) ---
    session_cookie = request.cookies.get(_SESSION_COOKIE_NAME)
    if session_cookie:
        result = await self._validate_session_cookie(session_cookie)
        if result:
            session, user = result
            request.state.user_id = user.id
            request.state.user = user
            return await call_next(request)
        # Invalid cookie — clear it in response
        response = await self._handle_fallback_auth(request, call_next)
        response.delete_cookie(_SESSION_COOKIE_NAME, path="/")
        return response

    return await self._handle_fallback_auth(request, call_next)

async def _handle_fallback_auth(self, request: Request, call_next) -> Response:
    """Handle auth when no valid session cookie is present."""
    # Rate limit auth endpoints
    if self._oidc_mode or self._basic_mode:
        client_ip = self._get_client_ip(request)
        allowed, retry_after = self._check_auth_rate_limit(client_ip)
        if not allowed:
            logger.warning("Rate limit exceeded for auth from IP: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Zu viele Authentifizierungsversuche. Bitte warte einen Moment.",
                    "retry_after": retry_after,
                },
            )

    if self._oidc_mode:
        return await self._handle_oidc(request, call_next)
    if self._basic_mode:
        return await self._handle_basic_auth(request, call_next)

    # Anonymous mode
    if not settings.allow_anonymous:
        # If browser request, redirect to /login; otherwise 401
        accept = request.headers.get("Accept", "")
        if "text/html" in accept and not request.url.path.startswith("/api"):
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/login")
        return JSONResponse(
            status_code=401,
            content={"detail": "Anmeldung erforderlich."},
        )

    request.state.user_id = "anonymous"
    request.state.user = None
    return await call_next(request)
```

### Step 3: `_validate_session_cookie`-Methode hinzufügen

```python
async def _validate_session_cookie(self, session_id: str) -> Optional[tuple]:
    """Validate session cookie. Returns (session, user) or None."""
    try:
        from app.services.user_service import user_service
        result = user_service.get_session(session_id)
        return result
    except Exception as exc:
        logger.warning("Session validation error: %s", exc)
        return None
```

### Step 4: OIDC-Handler: Auto-Provisioning für neue User

In `_handle_oidc` nach erfolgreicher JWT-Validierung User auto-provisionen:

```python
async def _handle_oidc(self, request: Request, call_next) -> Response:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Bearer-Token erforderlich."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]
    payload = await self._validate_jwt(token)
    if payload is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Ungültiger oder abgelaufener Token."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = payload.get("sub", "oidc-user")
    # Auto-provision OIDC user on first login
    try:
        from app.services.user_service import user_service
        preferred_username = payload.get("preferred_username") or payload.get("email") or subject
        user = user_service.provision_oidc_user(subject=subject, username=preferred_username)
        request.state.user_id = user.id
        request.state.user = user
    except Exception as exc:
        logger.warning("OIDC auto-provisioning failed: %s", exc)
        request.state.user_id = subject
        request.state.user = None

    return await call_next(request)
```

### Step 5: Existing `_handle_basic_auth` — user auf state schreiben

Am Ende von `_handle_basic_auth` vor `return await call_next(request)`:

```python
    request.state.user_id = username
    request.state.user = None  # Basic auth has no User object in DB
    return await call_next(request)
```

### Step 6: Smoke-Test

```bash
python3 -c "from app.middleware.auth import AuthMiddleware; print('OK')"
```

### Step 7: Commit

```bash
git add app/middleware/auth.py
git commit -m "feat(auth): add session cookie validation and ALLOW_ANONYMOUS support"
```

---

## Task 9: DB-Migration + Admin-Bootstrap

**Files:**
- Modify: `app/db/database.py`
- Modify: `app/main.py` (lifespan)

### Was wird gemacht

1. `init_db()` erstellt neue Tabellen via `create_all()`
2. Migration-Schritt: anonyme Records in `history_records` und `usage_records` löschen
3. Admin-User aus `.env` anlegen (nur wenn noch keine User existieren)

### Step 1: `database.py` — migrate_db hinzufügen

```python
def migrate_db():
    """Run one-time migrations. Safe to call multiple times (idempotent)."""
    from sqlalchemy import text as sa_text
    with engine.connect() as conn:
        # Remove legacy anonymous records (user decision: no transfer)
        conn.execute(sa_text("DELETE FROM history_records WHERE user_id = 'anonymous'"))
        conn.execute(sa_text("DELETE FROM usage_records WHERE user_id = 'anonymous'"))
        conn.commit()
    logger.info("DB migration: anonymous records removed (idempotent).")
```

### Step 2: `main.py` lifespan — migrate_db + ensure_admin_user aufrufen

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.database import init_db, migrate_db
    from app.services.user_service import user_service as _user_service

    logger.info("Senten startet — Datenbank wird initialisiert …")
    init_db()
    migrate_db()
    _user_service.ensure_admin_user()
    logger.info("Datenbank bereit.")
    yield
    logger.info("Senten wird beendet.")
```

### Step 3: Logger in database.py hinzufügen

Am Anfang von `database.py`:

```python
import logging
logger = logging.getLogger(__name__)
```

### Step 4: Smoke-Test (Server starten)

```bash
uvicorn app.main:app --reload --port 8001 &
sleep 3
curl -s http://localhost:8001/health | python3 -m json.tool
kill %1
```

Erwartet: `{"status": "ok", "service": "Senten"}`

### Step 5: Commit

```bash
git add app/db/database.py app/main.py
git commit -m "feat(db): add migration for anonymous records and admin bootstrap"
```

---

## Task 10: main.py — Neue Router registrieren

**Files:**
- Modify: `app/main.py`

### Step 1: Router-Imports + Registrierung

```python
# Vorher:
from app.routers import auth, history, translate, usage

# Nachher:
from app.routers import admin, auth, history, profile, translate, usage
```

```python
# Hinzufügen:
app.include_router(profile.router, prefix="/api", tags=["Profile"])
app.include_router(admin.router, prefix="/api", tags=["Admin"])
```

### Step 2: `/login`-Route hinzufügen

```python
@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Serve the login page."""
    csp_nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "csp_nonce": csp_nonce},
    )
```

### Step 3: Import-Check

```bash
python3 -c "from app.main import app; print('OK')"
```

### Step 4: Commit

```bash
git add app/main.py
git commit -m "feat(main): register profile and admin routers, add /login route"
```

---

## Task 11: Login-Seite (templates/login.html)

**Files:**
- Create: `templates/login.html`

### Step 1: Erstelle minimale Login-Seite

```html
<!DOCTYPE html>
<html lang="de" data-theme="light-blue">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Senten — Anmelden</title>
  <link rel="stylesheet" href="/static/css/styles.css">
  <link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
  <nonce>{{ csp_nonce }}</nonce>
</head>
<body class="login-page">
  <div class="login-container">
    <div class="login-card">
      <div class="login-logo">
        <img src="/static/img/logo-large.svg" alt="Senten" height="36">
      </div>
      <h1 class="login-title">Anmelden</h1>
      <form id="login-form" class="login-form" novalidate>
        <div class="form-group">
          <label for="username">Benutzername</label>
          <input type="text" id="username" name="username" autocomplete="username"
                 required autofocus class="form-input">
        </div>
        <div class="form-group">
          <label for="password">Passwort</label>
          <input type="password" id="password" name="password"
                 autocomplete="current-password" required class="form-input">
        </div>
        <div class="form-group form-group--checkbox">
          <input type="checkbox" id="remember-me" name="remember_me">
          <label for="remember-me">Angemeldet bleiben</label>
        </div>
        <div id="login-error" class="login-error" hidden></div>
        <button type="submit" class="btn btn-primary btn-full" id="login-btn">
          Anmelden
        </button>
      </form>
    </div>
  </div>
  <script nonce="{{ csp_nonce }}">
    document.getElementById('login-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('login-btn');
      const errEl = document.getElementById('login-error');
      btn.disabled = true;
      btn.textContent = 'Anmelden…';
      errEl.hidden = true;
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            username: document.getElementById('username').value,
            password: document.getElementById('password').value,
            remember_me: document.getElementById('remember-me').checked,
          }),
        });
        if (res.ok) {
          window.location.replace('/');
        } else {
          const data = await res.json().catch(() => ({}));
          errEl.textContent = data.detail || 'Login fehlgeschlagen.';
          errEl.hidden = false;
        }
      } catch {
        errEl.textContent = 'Netzwerkfehler. Bitte erneut versuchen.';
        errEl.hidden = false;
      } finally {
        btn.disabled = false;
        btn.textContent = 'Anmelden';
      }
    });
  </script>
</body>
</html>
```

### Step 2: Login-CSS in `static/css/input.css` hinzufügen

Ergänze am Ende von `input.css`:

```css
/* ── Login Page ───────────────────────────────────────────────────── */
.login-page {
  @apply min-h-screen flex items-center justify-center;
  background: var(--bg);
}
.login-container {
  @apply w-full max-w-sm px-4;
}
.login-card {
  @apply rounded-xl p-8 shadow-lg;
  background: var(--surface);
  border: 1px solid var(--border);
}
.login-logo {
  @apply flex justify-center mb-6;
}
.login-title {
  @apply text-xl font-semibold text-center mb-6;
  color: var(--text-primary);
}
.login-form {
  @apply flex flex-col gap-4;
}
.form-group {
  @apply flex flex-col gap-1;
}
.form-group--checkbox {
  @apply flex-row items-center gap-2;
}
.form-group label {
  @apply text-sm font-medium;
  color: var(--text-secondary);
}
.form-input {
  @apply w-full rounded-lg px-3 py-2 text-sm outline-none;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-primary);
}
.form-input:focus {
  border-color: var(--color-interactive-default);
  box-shadow: 0 0 0 2px var(--color-interactive-subtle);
}
.btn-full {
  @apply w-full;
}
.login-error {
  @apply text-sm rounded-lg px-3 py-2;
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}
```

### Step 3: CSS neu bauen

```bash
npm run build:css
```

### Step 4: Commit

```bash
git add templates/login.html static/css/input.css static/css/styles.css
git commit -m "feat(ui): add login page"
```

---

## Task 12: Header-Updates in index.html

**Files:**
- Modify: `templates/index.html`

### Was wird gemacht

1. Profil-Button im Header (zeigt Username, öffnet Profil-Dropdown)
2. Logout-Button im Profil-Dropdown
3. Admin-Link nur für Admins sichtbar (JS-gesteuert via `/api/profile`)

Die Header-Änderungen sind minimal — JS lädt Profil beim Start und zeigt/versteckt Elemente.

### Step 1: Profil-Button zum Header hinzufügen

Im Header (Zeile nach dem Theme-Picker, vor `</header>`), füge hinzu:

```html
<!-- Profil-Button (nur wenn eingeloggt, via JS gesteuert) -->
<div id="user-menu-wrap" class="relative" hidden>
  <button id="user-menu-btn" class="btn btn-ghost flex items-center gap-2 text-sm"
          aria-haspopup="true" aria-expanded="false">
    <i class="fas fa-user-circle"></i>
    <span id="user-display-name">Profil</span>
    <i class="fas fa-chevron-down text-xs"></i>
  </button>
  <div id="user-dropdown" class="theme-dropdown" hidden>
    <div id="user-dropdown-admin" hidden>
      <a href="/admin" class="theme-option flex items-center gap-2">
        <i class="fas fa-cog w-4"></i> Admin
      </a>
      <div class="theme-separator"></div>
    </div>
    <button id="user-logout-btn" class="theme-option flex items-center gap-2 text-red-500">
      <i class="fas fa-sign-out-alt w-4"></i> Abmelden
    </button>
  </div>
</div>
```

### Step 2: Commit (nur HTML-Änderung, kein JS noch)

```bash
git add templates/index.html
git commit -m "feat(ui): add profile button placeholder in header"
```

---

## Task 13: Frontend-JS — Settings via API + Profil-Menü

**Files:**
- Modify: `static/js/app.js`

### Was wird gemacht

1. Beim Start: `GET /api/profile` aufrufen. Falls eingeloggt → Settings aus API anwenden, Profil-Menü zeigen. Falls 401 → localStorage-Fallback (anonymer Modus).
2. Jede Settings-Änderung (Theme, Akzentfarbe, Sprache, Engine, Formality) wird an `PUT /api/profile/settings` gespeichert.
3. Beim ersten Login: localStorage-Settings einmalig an die API senden, dann localStorage bereinigen.
4. Logout-Button: `POST /api/auth/logout` → Seite neu laden.

### Step 1: `_loadProfile`-Funktion hinzufügen

Am Anfang der `init()`-Methode (nach `this._initTheme()`), neue Methode einfügen:

```javascript
async _loadProfile() {
    try {
        const res = await fetch('/api/profile', { credentials: 'same-origin' });
        if (!res.ok) {
            // Not logged in — anonymous mode
            this.currentUser = null;
            return;
        }
        const profile = await res.json();
        this.currentUser = profile;
        this._applyProfileSettings(profile.settings);
        this._showUserMenu(profile);
    } catch {
        this.currentUser = null;
    }
},

_applyProfileSettings(s) {
    // Apply settings from server (overrides localStorage)
    if (s.theme) {
        this.applyTheme(s.theme, s.accent_color || null);
        localStorage.setItem('theme', s.theme);
        if (s.accent_color) localStorage.setItem('theme-accent-custom', s.accent_color);
        else localStorage.removeItem('theme-accent-custom');
    }
    if (s.target_lang) {
        const sel = document.getElementById('target-lang');
        if (sel) sel.value = s.target_lang;
    }
    if (s.formality) {
        document.querySelectorAll('.formality-select').forEach(el => el.value = s.formality);
    }
    if (s.diff_view !== undefined) {
        const btn = document.getElementById('diff-toggle');
        if (btn) btn.classList.toggle('active', s.diff_view);
        this.diffViewActive = s.diff_view;
    }
},

_showUserMenu(profile) {
    const wrap = document.getElementById('user-menu-wrap');
    const name = document.getElementById('user-display-name');
    const adminLink = document.getElementById('user-dropdown-admin');
    if (wrap) wrap.hidden = false;
    if (name) name.textContent = profile.display_name || profile.username;
    if (adminLink && profile.is_admin) adminLink.hidden = false;
},

async _saveProfileSetting(key, value) {
    if (!this.currentUser) return;  // anonymous — skip API call
    try {
        await fetch('/api/profile/settings', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [key]: value }),
        });
    } catch {
        // Silent fail — settings change is not critical
    }
},
```

### Step 2: Settings-Änderungen an API weiterleiten

In `applyTheme()` nach `localStorage.setItem('theme', themeId)`:

```javascript
this._saveProfileSetting('theme', themeId);
if (customAccent) this._saveProfileSetting('accent_color', customAccent);
else this._saveProfileSetting('accent_color', '');  // Reset
```

Gleiches Prinzip für Target-Lang-Wechsel, Formality, Engine-Toggle, Diff-View.

### Step 3: Logout-Button binden

In `bindEvents()`:

```javascript
const logoutBtn = document.getElementById('user-logout-btn');
if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
        window.location.replace('/');
    });
}

// User menu dropdown
const userMenuBtn = document.getElementById('user-menu-btn');
const userDropdown = document.getElementById('user-dropdown');
if (userMenuBtn && userDropdown) {
    userMenuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = !userDropdown.hidden;
        userDropdown.hidden = isOpen;
        userMenuBtn.setAttribute('aria-expanded', String(!isOpen));
    });
    document.addEventListener('click', () => { userDropdown.hidden = true; });
}
```

### Step 4: `_loadProfile` in `init()` aufrufen

In der `init()`-Methode nach `this._initTheme()`:

```javascript
await this._loadProfile();
```

> `init()` muss `async` sein wenn es das nicht schon ist.

### Step 5: Commit

```bash
git add static/js/app.js
git commit -m "feat(frontend): load profile from API, sync settings, add logout"
```

---

## Task 14: Admin-UI (templates/admin.html + static/js/admin.js)

**Files:**
- Create: `templates/admin.html`
- Create: `static/js/admin.js`
- Modify: `app/main.py` (Admin-Route hinzufügen)

### Step 1: admin.html erstellen (minimal, funktional)

```html
<!DOCTYPE html>
<html lang="de" data-theme="light-blue">
<head>
  <meta charset="UTF-8">
  <title>Senten — Admin</title>
  <link rel="stylesheet" href="/static/css/styles.css">
  <link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
</head>
<body class="admin-page">
  <header class="admin-header">
    <a href="/" class="admin-back">← Zurück zur App</a>
    <h1>Benutzerverwaltung</h1>
  </header>
  <main class="admin-main">
    <div class="admin-toolbar">
      <button id="btn-create-user" class="btn btn-primary">
        <i class="fas fa-plus"></i> Benutzer anlegen
      </button>
    </div>
    <div id="user-list" class="user-list">Laden…</div>
  </main>

  <!-- Modal: Benutzer anlegen -->
  <dialog id="modal-create" class="admin-modal">
    <form id="form-create" method="dialog">
      <h2>Neuer Benutzer</h2>
      <label>Benutzername <input type="text" name="username" required minlength="3"></label>
      <label>Passwort <input type="password" name="password" required minlength="8"></label>
      <label>Anzeigename <input type="text" name="display_name"></label>
      <label><input type="checkbox" name="is_admin"> Admin-Rechte</label>
      <div class="modal-actions">
        <button type="button" id="btn-cancel-create" class="btn btn-ghost">Abbrechen</button>
        <button type="submit" class="btn btn-primary">Anlegen</button>
      </div>
    </form>
  </dialog>

  <script src="/static/js/admin.js"></script>
</body>
</html>
```

### Step 2: admin.js erstellen

Vollständige Admin-UI-Logik (User laden, anlegen, deaktivieren, löschen, Passwort zurücksetzen):

```javascript
const Admin = {
    async init() {
        await this.loadUsers();
        this._bindEvents();
    },

    async loadUsers() {
        const res = await fetch('/api/admin/users', { credentials: 'same-origin' });
        if (res.status === 401 || res.status === 403) {
            document.getElementById('user-list').innerHTML =
                '<p class="error">Kein Zugriff. Bitte als Admin anmelden.</p>';
            return;
        }
        const users = await res.json();
        this._renderUsers(users);
    },

    _renderUsers(users) {
        const list = document.getElementById('user-list');
        if (!users.length) {
            list.innerHTML = '<p>Keine Benutzer vorhanden.</p>';
            return;
        }
        list.innerHTML = users.map(u => `
            <div class="user-card ${u.is_active ? '' : 'user-card--inactive'}" data-id="${u.id}">
                <div class="user-info">
                    <span class="user-name">${u.display_name || u.username}</span>
                    <span class="user-username">@${u.username}</span>
                    ${u.is_admin ? '<span class="badge badge-admin">Admin</span>' : ''}
                    ${!u.is_active ? '<span class="badge badge-inactive">Deaktiviert</span>' : ''}
                    <span class="user-meta">${u.auth_provider} · Letzter Login: ${u.last_login_at ? new Date(u.last_login_at).toLocaleDateString('de-DE') : 'Nie'}</span>
                </div>
                <div class="user-actions">
                    <button class="btn btn-sm btn-ghost" onclick="Admin.toggleActive('${u.id}', ${!u.is_active})">
                        ${u.is_active ? 'Deaktivieren' : 'Aktivieren'}
                    </button>
                    <button class="btn btn-sm btn-ghost" onclick="Admin.resetPassword('${u.id}')">
                        Passwort
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="Admin.deleteUser('${u.id}', '${u.username}')">
                        Löschen
                    </button>
                </div>
            </div>
        `).join('');
    },

    async toggleActive(id, newState) {
        await fetch(`/api/admin/users/${id}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: newState }),
        });
        await this.loadUsers();
    },

    async deleteUser(id, username) {
        if (!confirm(`Benutzer "${username}" wirklich löschen? Alle Daten werden gelöscht.`)) return;
        await fetch(`/api/admin/users/${id}`, {
            method: 'DELETE',
            credentials: 'same-origin',
        });
        await this.loadUsers();
    },

    async resetPassword(id) {
        const pw = prompt('Neues Passwort (mind. 8 Zeichen):');
        if (!pw || pw.length < 8) return;
        const res = await fetch(`/api/admin/users/${id}/password`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: pw }),
        });
        if (res.ok) alert('Passwort geändert.');
    },

    _bindEvents() {
        document.getElementById('btn-create-user').addEventListener('click', () => {
            document.getElementById('modal-create').showModal();
        });
        document.getElementById('btn-cancel-create').addEventListener('click', () => {
            document.getElementById('modal-create').close();
        });
        document.getElementById('form-create').addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const body = {
                username: fd.get('username'),
                password: fd.get('password'),
                display_name: fd.get('display_name') || null,
                is_admin: fd.has('is_admin'),
            };
            const res = await fetch('/api/admin/users', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (res.ok) {
                document.getElementById('modal-create').close();
                e.target.reset();
                await this.loadUsers();
            } else {
                const data = await res.json().catch(() => ({}));
                alert(data.detail || 'Fehler beim Anlegen.');
            }
        });
    },
};

Admin.init();
```

### Step 3: Admin-Route in `main.py` hinzufügen

```python
@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    """Serve the admin UI."""
    csp_nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse("admin.html", {"request": request, "csp_nonce": csp_nonce})
```

### Step 4: Commit

```bash
git add templates/admin.html static/js/admin.js app/main.py
git commit -m "feat(ui): add admin UI for user management"
```

---

## Task 15: Tests — UserService

**Files:**
- Create: `tests/test_user_service.py`

### Was wird getestet

- `create_user()`: Erfolg, doppelter Username → ValueError
- `get_user_by_username()`: existiert / existiert nicht
- `verify_password()`: korrekt / falsch
- `create_session()` + `get_session()`: gültig, abgelaufen, deaktivierter User
- `delete_session()`: Session weg nach Aufruf
- `update_user()`: is_active=False → Sessions werden gelöscht
- `delete_user()`: User + History + Usage + Settings weg
- `update_settings()`: partielles Update
- `ensure_admin_user()`: nur bei settings.admin_username/password + keine User

### Step 1: Tests schreiben

```python
"""Tests for UserService."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def fresh_service():
    """Each test gets an isolated UserService with in-memory DB."""
    # Tests use the conftest in-memory DB override
    yield


@pytest.fixture
def svc():
    return UserService()


class TestCreateUser:
    def test_creates_user_with_hash(self, svc):
        user = svc.create_user(username="alice", password="secret123")
        assert user.username == "alice"
        assert user.password_hash is not None
        assert user.is_admin is False
        assert user.auth_provider == "local"

    def test_creates_default_settings(self, svc):
        user = svc.create_user(username="bob", password="pw123456")
        settings = svc.get_settings(user.id)
        assert settings is not None
        assert settings.theme == "light-blue"
        assert settings.target_lang == "DE"

    def test_duplicate_username_raises(self, svc):
        svc.create_user(username="alice", password="pw12345678")
        with pytest.raises(ValueError):
            svc.create_user(username="alice", password="other123")

    def test_oidc_user_has_no_password(self, svc):
        user = svc.create_user(username="oidc_user", auth_provider="oidc", oidc_subject="sub123")
        assert user.password_hash is None
        assert user.oidc_subject == "sub123"


class TestPasswordVerification:
    def test_correct_password(self, svc):
        user = svc.create_user(username="verifytest", password="correct_pw!")
        assert svc.verify_password("correct_pw!", user.password_hash) is True

    def test_wrong_password(self, svc):
        user = svc.create_user(username="verifytest2", password="real_pw!")
        assert svc.verify_password("wrong_pw!", user.password_hash) is False

    def test_invalid_hash_returns_false(self, svc):
        assert svc.verify_password("any", "not_a_hash") is False


class TestSessionManagement:
    def test_create_and_get_session(self, svc):
        user = svc.create_user(username="sess_user", password="pw1234567")
        session = svc.create_session(user.id)
        result = svc.get_session(session.id)
        assert result is not None
        _, returned_user = result
        assert returned_user.id == user.id

    def test_expired_session_returns_none(self, svc):
        user = svc.create_user(username="expiry_user", password="pw1234567")
        session = svc.create_session(user.id)
        # Manually expire session
        from app.db.database import SessionLocal
        from app.db.models import Session as SessionModel
        with SessionLocal() as db:
            s = db.query(SessionModel).filter(SessionModel.id == session.id).first()
            s.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
        assert svc.get_session(session.id) is None

    def test_inactive_user_session_invalid(self, svc):
        user = svc.create_user(username="inactive_user", password="pw1234567")
        session = svc.create_session(user.id)
        svc.update_user(user.id, is_active=False)
        assert svc.get_session(session.id) is None

    def test_deactivate_user_deletes_sessions(self, svc):
        user = svc.create_user(username="deact_user", password="pw1234567")
        session = svc.create_session(user.id)
        svc.update_user(user.id, is_active=False)
        # Session should be gone from DB
        from app.db.database import SessionLocal
        from app.db.models import Session as SessionModel
        with SessionLocal() as db:
            count = db.query(SessionModel).filter(SessionModel.user_id == user.id).count()
        assert count == 0

    def test_delete_session(self, svc):
        user = svc.create_user(username="del_sess_user", password="pw1234567")
        session = svc.create_session(user.id)
        svc.delete_session(session.id)
        assert svc.get_session(session.id) is None


class TestDeleteUser:
    def test_delete_removes_user_and_cascade(self, svc):
        user = svc.create_user(username="del_user", password="pw12345678")
        user_id = user.id
        assert svc.delete_user(user_id) is True
        assert svc.get_user_by_id(user_id) is None
        assert svc.get_settings(user_id) is None

    def test_delete_nonexistent_returns_false(self, svc):
        assert svc.delete_user("nonexistent-id") is False


class TestUpdateSettings:
    def test_partial_update(self, svc):
        user = svc.create_user(username="settings_user", password="pw12345678")
        result = svc.update_settings(user.id, theme="dark-violet", diff_view=True)
        assert result.theme == "dark-violet"
        assert result.diff_view is True
        # Unchanged fields retain defaults
        assert result.target_lang == "DE"

    def test_update_nonexistent_returns_none(self, svc):
        assert svc.update_settings("fake-id", theme="dark-blue") is None
```

### Step 2: Tests ausführen

```bash
pytest tests/test_user_service.py -v
```

Alle Tests grün.

### Step 3: Commit

```bash
git add tests/test_user_service.py
git commit -m "test(user-service): add comprehensive UserService tests"
```

---

## Task 16: Tests — Auth-Router (Login / Logout)

**Files:**
- Create: `tests/test_auth_router.py`

### Step 1: Tests schreiben

```python
"""Tests for /api/auth/login and /api/auth/logout."""
import pytest
from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def test_user(client):
    """Create a test user before each test."""
    svc = UserService()
    svc.create_user(username="logintest", password="password123")
    yield


class TestLogin:
    def test_valid_login_sets_cookie(self, client):
        res = client.post("/api/auth/login", json={
            "username": "logintest",
            "password": "password123",
        })
        assert res.status_code == 200
        assert "senten_session" in res.cookies
        data = res.json()
        assert data["ok"] is True
        assert data["username"] == "logintest"

    def test_wrong_password_returns_401(self, client):
        res = client.post("/api/auth/login", json={
            "username": "logintest",
            "password": "wrongpassword",
        })
        assert res.status_code == 401

    def test_unknown_user_returns_401(self, client):
        res = client.post("/api/auth/login", json={
            "username": "nobody",
            "password": "pw12345678",
        })
        assert res.status_code == 401

    def test_inactive_user_cannot_login(self, client):
        svc = UserService()
        user = svc.get_user_by_username("logintest")
        svc.update_user(user.id, is_active=False)
        res = client.post("/api/auth/login", json={
            "username": "logintest",
            "password": "password123",
        })
        assert res.status_code == 401


class TestLogout:
    def test_logout_deletes_session(self, client):
        # Login
        res = client.post("/api/auth/login", json={
            "username": "logintest",
            "password": "password123",
        })
        assert res.status_code == 200
        session_id = res.cookies.get("senten_session")
        assert session_id

        # Logout
        res = client.post("/api/auth/logout")
        assert res.status_code == 200

        # Session should be gone
        svc = UserService()
        assert svc.get_session(session_id) is None

    def test_logout_without_cookie_is_ok(self, client):
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
```

### Step 2: Tests ausführen

```bash
pytest tests/test_auth_router.py -v
```

### Step 3: Commit

```bash
git add tests/test_auth_router.py
git commit -m "test(auth): add login and logout endpoint tests"
```

---

## Task 17: Tests — Profile-Router

**Files:**
- Create: `tests/test_profile.py`

### Step 1: Tests schreiben (Kernfälle)

```python
"""Tests for /api/profile endpoints."""
import pytest
from app.services.user_service import UserService


@pytest.fixture
def logged_in_client(client):
    """Client with active session for 'profiletest' user."""
    svc = UserService()
    svc.create_user(username="profiletest", password="password123")
    client.post("/api/auth/login", json={"username": "profiletest", "password": "password123"})
    return client


class TestGetProfile:
    def test_returns_profile_when_logged_in(self, logged_in_client):
        res = logged_in_client.get("/api/profile")
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "profiletest"
        assert "settings" in data
        assert data["settings"]["theme"] == "light-blue"

    def test_returns_401_without_session(self, client):
        res = client.get("/api/profile")
        assert res.status_code == 401


class TestUpdateSettings:
    def test_partial_update(self, logged_in_client):
        res = logged_in_client.put("/api/profile/settings", json={"theme": "dark-violet"})
        assert res.status_code == 200
        assert res.json()["theme"] == "dark-violet"

    def test_invalid_theme_returns_422(self, logged_in_client):
        res = logged_in_client.put("/api/profile/settings", json={"theme": "invalid"})
        assert res.status_code == 422

    def test_returns_401_without_session(self, client):
        res = client.put("/api/profile/settings", json={"theme": "dark-blue"})
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, logged_in_client):
        res = logged_in_client.put("/api/profile/password", json={
            "current_password": "password123",
            "new_password": "newpassword456",
        })
        assert res.status_code == 200

    def test_wrong_current_password(self, logged_in_client):
        res = logged_in_client.put("/api/profile/password", json={
            "current_password": "wrongpassword",
            "new_password": "newpassword456",
        })
        assert res.status_code == 401
```

### Step 2: Tests ausführen

```bash
pytest tests/test_profile.py -v
```

### Step 3: Commit

```bash
git add tests/test_profile.py
git commit -m "test(profile): add profile and settings endpoint tests"
```

---

## Task 18: Tests — Admin-Router

**Files:**
- Create: `tests/test_admin.py`

### Step 1: Tests schreiben

```python
"""Tests for /api/admin/* endpoints."""
import pytest
from app.services.user_service import UserService


@pytest.fixture
def admin_client(client):
    svc = UserService()
    svc.create_user(username="admin_user", password="admin123pw", is_admin=True)
    client.post("/api/auth/login", json={"username": "admin_user", "password": "admin123pw"})
    return client


@pytest.fixture
def regular_client(client):
    svc = UserService()
    svc.create_user(username="regular_user", password="user123pw")
    client.post("/api/auth/login", json={"username": "regular_user", "password": "user123pw"})
    return client


class TestListUsers:
    def test_admin_can_list_users(self, admin_client):
        res = admin_client.get("/api/admin/users")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_regular_user_gets_403(self, regular_client):
        res = regular_client.get("/api/admin/users")
        assert res.status_code == 403

    def test_anonymous_gets_401(self, client):
        res = client.get("/api/admin/users")
        assert res.status_code == 401


class TestCreateUser:
    def test_admin_creates_user(self, admin_client):
        res = admin_client.post("/api/admin/users", json={
            "username": "newuser",
            "password": "newpw12345",
        })
        assert res.status_code == 201
        assert res.json()["username"] == "newuser"

    def test_duplicate_username_returns_409(self, admin_client):
        admin_client.post("/api/admin/users", json={"username": "dup", "password": "pw12345678"})
        res = admin_client.post("/api/admin/users", json={"username": "dup", "password": "pw12345678"})
        assert res.status_code == 409


class TestUpdateUser:
    def test_deactivate_user(self, admin_client):
        svc = UserService()
        user = svc.create_user(username="to_deactivate", password="pw12345678")
        res = admin_client.put(f"/api/admin/users/{user.id}", json={"is_active": False})
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    def test_cannot_remove_own_admin_rights(self, admin_client):
        svc = UserService()
        user = svc.get_user_by_username("admin_user")
        res = admin_client.put(f"/api/admin/users/{user.id}", json={"is_admin": False})
        assert res.status_code == 400


class TestDeleteUser:
    def test_admin_deletes_user(self, admin_client):
        svc = UserService()
        user = svc.create_user(username="to_delete", password="pw12345678")
        res = admin_client.delete(f"/api/admin/users/{user.id}")
        assert res.status_code == 204

    def test_cannot_delete_self(self, admin_client):
        svc = UserService()
        user = svc.get_user_by_username("admin_user")
        res = admin_client.delete(f"/api/admin/users/{user.id}")
        assert res.status_code == 400
```

### Step 2: Tests ausführen

```bash
pytest tests/test_admin.py -v
```

### Step 3: Commit

```bash
git add tests/test_admin.py
git commit -m "test(admin): add admin user management tests"
```

---

## Task 19: Gesamte Test-Suite

**Files:**
- Modify: `tests/conftest.py` (nur wenn Session-Handling Anpassungen braucht)

### Step 1: Alle Tests ausführen

```bash
pytest tests/ -v --tb=short
```

Erwartet: Alle Tests grün (301 alte + neue Tests).

Wenn Fehler auftreten: Prüfe ob conftest.py die neuen Models kennt (init_db importiert alle Models via `from app.db import models`).

### Step 2: Bei Bedarf conftest.py anpassen

Falls neue DB-Models nicht registriert werden: in `tests/conftest.py` sicherstellen, dass `init_db()` alle Models lädt. Der Trick: `from app.db import models  # noqa` in `init_db()` importiert alle Models. Das passiert schon — kein Anpassungsbedarf.

### Step 3: Finaler Commit

```bash
git add -A
git commit -m "test(all): verify full suite passes with user management feature"
```

---

## Task 20: .env.example + Dokumentation

**Files:**
- Modify: `.env.example`
- Modify: `docs/features/benutzerverwaltung.md` (Status → Done)
- Modify: `docs/STATUS.md`

### Step 1: `.env.example` aktualisieren

Neue Variablen hinzufügen:

```bash
# User Management
# ALLOW_ANONYMOUS=true          # Allow unauthenticated access (default: true)
# ADMIN_USERNAME=admin          # Initial admin username
# ADMIN_PASSWORD=changeme       # Initial admin password (change immediately!)
# SESSION_LIFETIME_HOURS=24     # Session duration in hours (default: 24)
# SESSION_LIFETIME_REMEMBER_HOURS=720  # "Remember me" duration (default: 720 = 30 days)
```

### Step 2: Feature-Status aktualisieren

In `docs/features/benutzerverwaltung.md`: Status → Done

In `docs/STATUS.md`:
- Benutzerverwaltung aus "Features In Progress" → "Completed This Week"
- Version check: Major Feature → v2.8.0

### Step 3: Final-Commit

```bash
git add .env.example docs/
git commit -m "docs: update env.example and mark benutzerverwaltung as done"
```

---

## Abschlussprüfung (Checkliste)

Vor dem Commit überprüfen:

- [ ] `pytest tests/ -q` → alle Tests grün
- [ ] `python3 -c "from app.main import app; print('OK')"` → OK
- [ ] Server startet: `uvicorn app.main:app --reload`
- [ ] Login unter `http://localhost:8000/login` funktioniert (mit `ADMIN_USERNAME`/`ADMIN_PASSWORD`)
- [ ] `/api/profile` gibt 401 ohne Cookie, Profil nach Login
- [ ] `/api/admin/users` gibt 403 für Nicht-Admins
- [ ] Admin-UI unter `http://localhost:8000/admin` zugänglich
- [ ] `ALLOW_ANONYMOUS=true` (Default): App nutzbar ohne Login
- [ ] Alle bestehenden Tests (301) bleiben grün

---

## Version-Bump

Feature ist Major (neue API-Endpunkte, DB-Schema, Auth-Schicht):

```
v2.7.3 → v2.8.0
```

Nach Abschluss in `app/config.py`:
```python
VERSION = "2.8.0"
```
