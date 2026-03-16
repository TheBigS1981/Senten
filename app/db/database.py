import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def _build_engine():
    db_url = settings.database_url
    kwargs = {}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        # Enable WAL mode for better concurrent read performance with SQLite
        engine = create_engine(db_url, **kwargs)

        @event.listens_for(engine, "connect")
        def set_wal_mode(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine
    return create_engine(db_url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables. Called once at application startup."""
    from app.db import models  # noqa: F401 — import models to register them

    Base.metadata.create_all(bind=engine)


def migrate_db():
    """Run one-time data migrations. Safe to call multiple times (idempotent).

    Current migrations:
    - Remove legacy anonymous records from history_records and usage_records.
      These records were created before user management was introduced.
      Runs once per startup; rows are gone after the first run, so subsequent
      DELETE statements are no-ops and always safe to re-execute.
    - Add users.email column (nullable, unique) for Gravatar support.
    """
    from sqlalchemy import text as sa_text

    with engine.connect() as conn:
        conn.execute(sa_text("DELETE FROM history_records WHERE user_id = 'anonymous'"))
        conn.execute(sa_text("DELETE FROM usage_records WHERE user_id = 'anonymous'"))
        conn.commit()
    logger.info("DB migration: anonymous records removed (idempotent).")

    # SQLite does not support ALTER TABLE ... ADD COLUMN ... UNIQUE directly
    # when the table already contains rows (raises "Cannot add a UNIQUE column").
    # The portable workaround is: add the column without a constraint, then
    # create a separate UNIQUE INDEX — both steps are individually idempotent.
    try:
        with engine.connect() as conn:
            conn.execute(sa_text("ALTER TABLE users ADD COLUMN email VARCHAR"))
            conn.commit()
            logger.info("Migration: users.email column added")
    except Exception as exc:
        # OperationalError("duplicate column name: email") → column already exists
        # OperationalError("Cannot add a UNIQUE column") → old migration attempt
        # Both are expected and safe to ignore on repeat runs.
        msg = str(exc).lower()
        if any(
            phrase in msg
            for phrase in (
                "duplicate column name",
                "already exists",
                "cannot add a unique column",
            )
        ):
            logger.debug(
                "Migration: users.email column already present — skipping ADD COLUMN"
            )
        else:
            raise

    try:
        with engine.connect() as conn:
            conn.execute(
                sa_text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
                    " WHERE email IS NOT NULL"
                )
            )
            conn.commit()
            logger.info("Migration: unique index on users.email created")
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg:
            logger.debug("Migration: ix_users_email already exists — skipping")
        else:
            raise

    # v2.12.0: Add ui_language column to user_settings (for existing installations)
    try:
        with engine.connect() as conn:
            conn.execute(
                sa_text(
                    "ALTER TABLE user_settings ADD COLUMN ui_language VARCHAR NOT NULL DEFAULT 'en'"
                )
            )
            conn.commit()
            logger.info("Migration: user_settings.ui_language column added")
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate column name" in msg or "already exists" in msg:
            logger.debug(
                "Migration: user_settings.ui_language already present — skipping"
            )
        else:
            raise

    # Bug C: Add token tracking columns to usage_records (for existing installations)
    # Fresh installs get these via init_db() → models.py; existing DBs need migration.
    _ALLOWED_COLS = {"word_count", "input_tokens", "output_tokens"}
    for col, typedef in [
        ("word_count", "INTEGER NOT NULL DEFAULT 0"),
        ("input_tokens", "INTEGER NOT NULL DEFAULT 0"),
        ("output_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        # Whitelist validation to prevent SQL injection
        assert col in _ALLOWED_COLS, f"Invalid column name: {col}"
        try:
            with engine.connect() as conn:
                conn.execute(
                    sa_text(f"ALTER TABLE usage_records ADD COLUMN {col} {typedef}")
                )
                conn.commit()
                logger.info(f"Migration: usage_records.{col} column added")
        except Exception as exc:
            msg = str(exc).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                logger.debug(
                    f"Migration: usage_records.{col} already present — skipping"
                )
            else:
                raise
