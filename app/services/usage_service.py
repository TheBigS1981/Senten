"""Usage tracking service — records character consumption per operation."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import UsageRecord

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_day() -> datetime:
    now = _now_utc()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month() -> datetime:
    now = _now_utc()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class UsageService:
    """Records and queries character usage from SQLite."""

    def __init__(self) -> None:
        self.monthly_limit: int = settings.monthly_char_limit

    def record_usage(
        self,
        user_id: str,
        characters: int,
        operation_type: str,
        target_language: Optional[str] = None,
        word_count: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Persist a usage record. Silently logs on DB error instead of propagating."""
        try:
            with SessionLocal() as db:
                record = UsageRecord(
                    user_id=user_id,
                    characters_used=characters,
                    operation_type=operation_type,
                    target_language=target_language,
                    word_count=word_count,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                db.add(record)
                db.commit()
        except Exception as exc:
            logger.error("Nutzungsdaten konnten nicht gespeichert werden: %s", exc)

    def get_usage_stats(self, user_id: str = "anonymous") -> dict:
        """Return a dict with daily/monthly totals, split by operation type.

        Uses a single aggregated query to fetch all stats at once,
        avoiding the N+1 query pattern.
        """
        day_start = _start_of_day()
        month_start = _start_of_month()

        daily_translate = 0
        daily_write = 0
        monthly_translate = 0
        monthly_write = 0

        try:
            with SessionLocal() as db:
                # Single aggregated query: get monthly totals by operation type
                monthly_rows = (
                    db.query(
                        UsageRecord.operation_type,
                        func.sum(UsageRecord.characters_used).label("total"),
                    )
                    .filter(
                        UsageRecord.user_id == user_id,
                        UsageRecord.created_at >= month_start,
                    )
                    .group_by(UsageRecord.operation_type)
                    .all()
                )

                # Process monthly totals
                for row in monthly_rows:
                    op = row.operation_type
                    total = int(row.total or 0)
                    if op == "translate":
                        monthly_translate = total
                    elif op == "write":
                        monthly_write = total

                # Single query for daily totals - get both operation types at once
                daily_rows = (
                    db.query(
                        UsageRecord.operation_type,
                        func.sum(UsageRecord.characters_used).label("total"),
                    )
                    .filter(
                        UsageRecord.user_id == user_id,
                        UsageRecord.created_at >= day_start,
                    )
                    .group_by(UsageRecord.operation_type)
                    .all()
                )

                # Process daily totals
                for row in daily_rows:
                    op = row.operation_type
                    total = int(row.total or 0)
                    if op == "translate":
                        daily_translate = total
                    elif op == "write":
                        daily_write = total

        except Exception as exc:
            logger.error("Fehler beim Lesen der Nutzungsstatistiken: %s", exc)

        daily_total = daily_translate + daily_write
        monthly_total = monthly_translate + monthly_write
        remaining = max(0, self.monthly_limit - monthly_total)
        percent_used = (
            (monthly_total / self.monthly_limit * 100)
            if self.monthly_limit > 0
            else 0.0
        )

        return {
            "daily_translate": daily_translate,
            "daily_write": daily_write,
            "daily_total": daily_total,
            "monthly_translate": monthly_translate,
            "monthly_write": monthly_write,
            "monthly_total": monthly_total,
            "monthly_limit": self.monthly_limit,
            "remaining": remaining,
            "percent_used": round(percent_used, 2),
        }


# Module-level singleton
usage_service = UsageService()
