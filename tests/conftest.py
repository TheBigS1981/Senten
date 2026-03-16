"""Shared test fixtures for Senten.

Uses an in-memory SQLite database so tests are isolated from the
production database file.

StaticPool keeps a single connection alive for the entire test session so that
the in-memory SQLite database (which only exists for the lifetime of a
connection) is accessible from all sessions created via TestingSessionLocal.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Point to an in-memory SQLite database BEFORE importing the application
# Use os.environ[] (not setdefault) for values that must override .env file settings.
# Pydantic BaseSettings reads .env directly, so env vars must be set before import.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEEPL_API_KEY"] = ""  # Forces mock mode
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DISABLE_RATE_LIMIT"] = "1"  # Disable rate limiting in tests
os.environ["SESSION_COOKIE_SECURE"] = "false"  # Allow cookies over HTTP in tests
os.environ["LLM_PROVIDER"] = ""  # Disable LLM in tests (overrides .env file)

import app.db.database as _db_module  # noqa: E402
import app.services.history_service as _history_module  # noqa: E402
import app.services.usage_service as _usage_module  # noqa: E402
import app.services.user_service as _user_module  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.db.models import (  # noqa: E402
    HistoryRecord,
    Session,
    UsageRecord,
    User,
    UserSettings,
)
from app.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402

# Disable rate limiting in tests entirely
# This must happen AFTER the app is imported (routes are registered at import time)
limiter.enabled = False

# ---------------------------------------------------------------------------
# In-memory database engine shared across the entire test session.
# StaticPool forces SQLAlchemy to reuse the same underlying connection so the
# in-memory SQLite database survives across all sessions / requests.
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite:///:memory:"

_test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables in the shared in-memory database once per session.

    Also patches the module-level SessionLocal used by UsageService so that
    instances created outside FastAPI dependency injection (e.g., unit tests)
    also hit the in-memory database.
    """
    # Create tables
    Base.metadata.create_all(bind=_test_engine)

    # Patch SessionLocal in all service modules so they hit the in-memory test DB.
    _original_db_session = _db_module.SessionLocal
    _original_usage_session = _usage_module.SessionLocal
    _original_history_session = _history_module.SessionLocal
    _original_user_session = _user_module.SessionLocal
    _db_module.SessionLocal = TestingSessionLocal
    _usage_module.SessionLocal = TestingSessionLocal
    _history_module.SessionLocal = TestingSessionLocal
    _user_module.SessionLocal = TestingSessionLocal

    yield

    # Restore originals and tear down
    _db_module.SessionLocal = _original_db_session
    _usage_module.SessionLocal = _original_usage_session
    _history_module.SessionLocal = _original_history_session
    _user_module.SessionLocal = _original_user_session
    Base.metadata.drop_all(bind=_test_engine)


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Replace the real database dependency with the test database."""
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """FastAPI TestClient that uses the in-memory database."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_test_db():
    """Clean database before each test to ensure isolation."""

    def _clean():
        try:
            with TestingSessionLocal() as db:
                db.query(Session).delete()
                db.query(UserSettings).delete()
                db.query(User).delete()
                db.query(HistoryRecord).delete()
                db.query(UsageRecord).delete()
                db.commit()
        except Exception:
            pass

    _clean()
    yield
    _clean()
