"""History service — manages translation history records."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import HistoryRecord

logger = logging.getLogger(__name__)

MAX_HISTORY_RECORDS = 100


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class HistoryService:
    """Manages translation/write history records in SQLite."""

    def __init__(self) -> None:
        self.max_records: int = getattr(
            settings, "history_max_records", MAX_HISTORY_RECORDS
        )

    def _enforce_limit(self, db: Session, user_id: str) -> None:
        """Delete oldest records if user exceeds max limit.

        Uses a single subquery to find records to keep, avoiding a
        count-then-delete race condition under concurrent requests.
        """
        # IDs of the newest records the user is allowed to keep
        keep_subq = (
            db.query(HistoryRecord.id)
            .filter(HistoryRecord.user_id == user_id)
            .order_by(HistoryRecord.created_at.desc())
            .limit(self.max_records - 1)  # -1 to make room for the new record
            .subquery()
        )

        deleted = (
            db.query(HistoryRecord)
            .filter(
                HistoryRecord.user_id == user_id,
                ~HistoryRecord.id.in_(db.query(keep_subq.c.id)),
            )
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()
            logger.info(
                "Deleted %d oldest history records for user=%s", deleted, user_id
            )

    _DEDUP_WINDOW_SECONDS = 60
    """Zeitfenster in Sekunden, innerhalb dessen identische Einträge als Duplikat gelten.

    Bug D fix: Verhindert doppelte History-Einträge bei Page-Reload (sessionStorage wird
    geleert) oder Frontend-Race-Conditions. Gleiche Kombination aus user_id + operation_type
    + source_text + target_lang innerhalb dieses Fensters wird nur einmal gespeichert.
    """

    def _find_duplicate(
        self,
        db: Session,
        user_id: str,
        operation_type: str,
        source_text: str,
        target_lang: str,
    ) -> Optional[HistoryRecord]:
        """Prüft ob ein identischer Eintrag innerhalb des Dedup-Fensters existiert."""
        cutoff = _now_utc() - timedelta(seconds=self._DEDUP_WINDOW_SECONDS)
        return (
            db.query(HistoryRecord)
            .filter(
                HistoryRecord.user_id == user_id,
                HistoryRecord.operation_type == operation_type,
                HistoryRecord.source_text == source_text,
                HistoryRecord.target_lang == target_lang,
                HistoryRecord.created_at >= cutoff,
            )
            .first()
        )

    def add_record(
        self,
        user_id: str,
        operation_type: str,
        source_text: str,
        target_text: str,
        source_lang: Optional[str],
        target_lang: str,
    ) -> tuple[HistoryRecord, bool]:
        """Add a new history record. Enforces max limit and deduplication.

        Returns:
            (record, created): record ist der neue oder existierende Eintrag.
                               created=True wenn neu angelegt, False wenn Duplikat.
        """
        try:
            with SessionLocal() as db:
                # Dedup-Prüfung: Gleicher Eintrag innerhalb von 60 Sekunden?
                existing = self._find_duplicate(
                    db, user_id, operation_type, source_text, target_lang
                )
                if existing:
                    logger.debug(
                        "History dedup: Duplikat unterdrückt für user=%s (id=%d, Fenster=%ds)",
                        user_id,
                        existing.id,
                        self._DEDUP_WINDOW_SECONDS,
                    )
                    return existing, False

                self._enforce_limit(db, user_id)
                record = HistoryRecord(
                    user_id=user_id,
                    operation_type=operation_type,
                    source_text=source_text,
                    target_text=target_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
                db.add(record)
                db.commit()
                db.refresh(record)
                logger.debug(
                    "Added history record id=%d for user=%s", record.id, user_id
                )
                return record, True
        except Exception as exc:
            logger.error("Could not save history record: %s", exc)
            raise

    def get_history(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[HistoryRecord], int]:
        """Get history records for a user, newest first. Returns (records, total_count)."""
        try:
            with SessionLocal() as db:
                # Get total count
                total = (
                    db.query(func.count(HistoryRecord.id))
                    .filter(HistoryRecord.user_id == user_id)
                    .scalar()
                    or 0
                )

                records = (
                    db.query(HistoryRecord)
                    .filter(HistoryRecord.user_id == user_id)
                    .order_by(HistoryRecord.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )
                return records, total
        except Exception as exc:
            logger.error("Could not fetch history: %s", exc)
            return [], 0

    def get_record(self, user_id: str, record_id: int) -> Optional[HistoryRecord]:
        """Get a single history record by ID."""
        try:
            with SessionLocal() as db:
                record = (
                    db.query(HistoryRecord)
                    .filter(
                        HistoryRecord.id == record_id,
                        HistoryRecord.user_id == user_id,
                    )
                    .first()
                )
                return record
        except Exception as exc:
            logger.error("Could not fetch history record %d: %s", record_id, exc)
            return None

    def delete_record(self, user_id: str, record_id: int) -> bool:
        """Delete a single history record. Returns True if deleted."""
        try:
            with SessionLocal() as db:
                record = (
                    db.query(HistoryRecord)
                    .filter(
                        HistoryRecord.id == record_id,
                        HistoryRecord.user_id == user_id,
                    )
                    .first()
                )
                if record:
                    db.delete(record)
                    db.commit()
                    logger.info(
                        "Deleted history record id=%d for user=%s", record_id, user_id
                    )
                    return True
                return False
        except Exception as exc:
            logger.error("Could not delete history record %d: %s", record_id, exc)
            return False

    def delete_all(self, user_id: str) -> int:
        """Delete all history records for a user. Returns count deleted."""
        try:
            with SessionLocal() as db:
                count = (
                    db.query(HistoryRecord)
                    .filter(HistoryRecord.user_id == user_id)
                    .delete(synchronize_session=False)
                )
                db.commit()
                logger.info("Deleted %d history records for user=%s", count, user_id)
                return count
        except Exception as exc:
            logger.error("Could not delete history for user=%s: %s", user_id, exc)
            return 0


history_service = HistoryService()
