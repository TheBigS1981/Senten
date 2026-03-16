import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String

from app.db.database import Base


def _now_utc():
    return datetime.now(timezone.utc)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="anonymous", nullable=False)
    characters_used = Column(Integer, nullable=False)
    operation_type = Column(String, nullable=False)  # "translate" | "write"
    target_language = Column(String, nullable=True)
    word_count = Column(Integer, nullable=False, default=0, server_default="0")
    input_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    output_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    __table_args__ = (
        # Efficient queries for daily/monthly aggregation
        Index("ix_usage_user_created", "user_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<UsageRecord id={self.id} user={self.user_id!r} "
            f"op={self.operation_type!r} chars={self.characters_used}>"
        )


class HistoryRecord(Base):
    __tablename__ = "history_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, default="anonymous", nullable=False)
    operation_type = Column(String, nullable=False)  # "translate" | "write"
    source_text = Column(String, nullable=False)
    target_text = Column(String, nullable=False)
    source_lang = Column(String, nullable=True)
    target_lang = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    __table_args__ = (Index("ix_history_user_created", "user_id", "created_at"),)

    def __repr__(self):
        return (
            f"<HistoryRecord id={self.id} user={self.user_id!r} "
            f"op={self.operation_type!r} target={self.target_lang!r}>"
        )


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # null for OIDC-only users
    display_name = Column(String, nullable=True)
    email = Column(String, nullable=True, unique=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    auth_provider = Column(String, default="local", nullable=False)  # "local" | "oidc"
    oidc_subject = Column(String, nullable=True, unique=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    # Note: username has unique=True on the Column, which creates an implicit index.
    # No explicit __table_args__ needed — avoids duplicate index creation.

    def __repr__(self):
        return f"<User id={self.id!r} username={self.username!r} admin={self.is_admin}>"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    def __repr__(self):
        return f"<Session id={self.id!r} user_id={self.user_id!r}>"


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme = Column(String, default="light-blue", nullable=False)
    accent_color = Column(String, nullable=True)
    source_lang = Column(String, nullable=True)
    target_lang = Column(String, default="DE", nullable=False)
    engine_translate = Column(String, default="deepl", nullable=False)
    engine_write = Column(String, default="deepl", nullable=False)
    diff_view = Column(Boolean, default=False, nullable=False)
    ui_language = Column(String, default="en", server_default="en", nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    def __repr__(self):
        return f"<UserSettings user_id={self.user_id!r} theme={self.theme!r}>"
