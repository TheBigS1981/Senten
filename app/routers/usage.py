"""Usage statistics API endpoint."""

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlalchemy import inspect as sqlalchemy_inspect

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import UsageRecord as UsageRecordModel
from app.models.schemas import UsageStats
from app.services.deepl_service import deepl_service
from app.services.llm_service import llm_service
from app.services.usage_service import usage_service
from app.utils import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache(maxsize=1)
def _get_table_columns() -> tuple[bool, bool]:
    """Cache column existence check at module load time.

    Returns a tuple of (has_word_count, has_tokens).
    """
    try:
        with SessionLocal() as db:
            inspector = sqlalchemy_inspect(db.bind)
            columns = [c["name"] for c in inspector.get_columns("usage_records")]
            has_word_count = "word_count" in columns
            has_tokens = "input_tokens" in columns and "output_tokens" in columns
            return has_word_count, has_tokens
    except Exception as exc:
        logger.warning("Failed to inspect table columns: %s", exc)
        return False, False


@router.get("/usage/summary")
async def get_usage_summary():
    """Return cumulative usage stats for the last 4 weeks.

    Falls die neuen DB-Spalten (word_count, input_tokens, output_tokens) nicht existieren,
    wird ein Fallback verwendet: words = characters, tokens = 0.
    """
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)

    has_word_count, has_tokens = _get_table_columns()

    with SessionLocal() as db:
        try:
            if has_word_count:
                translate_stats = (
                    db.query(
                        func.coalesce(func.sum(UsageRecordModel.word_count), 0),
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                    )
                    .filter(
                        UsageRecordModel.operation_type == "translate",
                        UsageRecordModel.created_at >= four_weeks_ago,
                    )
                    .first()
                )
                write_stats = (
                    db.query(
                        func.coalesce(func.sum(UsageRecordModel.word_count), 0),
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                    )
                    .filter(
                        UsageRecordModel.operation_type == "write",
                        UsageRecordModel.created_at >= four_weeks_ago,
                    )
                    .first()
                )
            else:
                # Fallback: use characters_used as word count approximation
                translate_stats = (
                    db.query(
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                    )
                    .filter(
                        UsageRecordModel.operation_type == "translate",
                        UsageRecordModel.created_at >= four_weeks_ago,
                    )
                    .first()
                )
                write_stats = (
                    db.query(
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                        func.coalesce(func.sum(UsageRecordModel.characters_used), 0),
                    )
                    .filter(
                        UsageRecordModel.operation_type == "write",
                        UsageRecordModel.created_at >= four_weeks_ago,
                    )
                    .first()
                )

            # LLM tokens - only query if columns exist
            if has_tokens:
                llm_stats = (
                    db.query(
                        func.coalesce(func.sum(UsageRecordModel.input_tokens), 0),
                        func.coalesce(func.sum(UsageRecordModel.output_tokens), 0),
                    )
                    .filter(
                        UsageRecordModel.created_at >= four_weeks_ago,
                        UsageRecordModel.input_tokens > 0,
                    )
                    .first()
                )
            else:
                llm_stats = (0, 0)
        except Exception as e:
            # Graceful fallback on any DB error
            logger.warning(f"Usage summary query failed: {e}")
            translate_stats = (0, 0)
            write_stats = (0, 0)
            llm_stats = (0, 0)

    llm_configured = llm_service.is_configured()

    translate_words = int(translate_stats[0] or 0) if translate_stats else 0
    translate_chars = int(translate_stats[1] or 0) if translate_stats else 0
    write_words = int(write_stats[0] or 0) if write_stats else 0
    write_chars = int(write_stats[1] or 0) if write_stats else 0
    llm_in = int(llm_stats[0] or 0) if llm_stats else 0
    llm_out = int(llm_stats[1] or 0) if llm_stats else 0

    return {
        "period": "4 weeks",
        "translate": {
            "words": translate_words,
            "characters": translate_chars,
        },
        "write": {
            "words": write_words,
            "characters": write_chars,
        },
        # Bug C fix: llm-Block immer zurückgeben, nie None.
        # Vorher wurde llm=null geliefert wenn llm_service.is_configured() False war —
        # das verhinderte die 4-Wochen-Token-Anzeige im Header auch wenn Tokens in der
        # DB lagen (z.B. über LiteLLM). 'configured'-Flag erlaubt dem Frontend weiterhin
        # zu unterscheiden ob LLM aktuell nutzbar ist.
        "llm": {
            "input_tokens": llm_in,
            "output_tokens": llm_out,
            "configured": llm_configured,
        },
    }


@router.get("/usage")
async def get_usage(request: Request):
    """Return combined local and DeepL API usage statistics."""
    user_id = get_user_id(request)

    local_stats = usage_service.get_usage_stats(user_id)
    deepl_stats = await deepl_service.async_get_usage()

    logger.debug("Usage requested by user=%s", user_id)

    deepl_char_count = deepl_stats.get("character_count", 0)
    deepl_char_limit = deepl_stats.get("character_limit", settings.monthly_char_limit)
    deepl_percent = (
        (deepl_char_count / deepl_char_limit * 100) if deepl_char_limit > 0 else 0.0
    )

    return {
        "local": UsageStats(
            daily_translate=local_stats["daily_translate"],
            daily_write=local_stats["daily_write"],
            daily_total=local_stats["daily_total"],
            monthly_translate=local_stats["monthly_translate"],
            monthly_write=local_stats["monthly_write"],
            monthly_total=local_stats["monthly_total"],
            monthly_limit=local_stats["monthly_limit"],
            remaining=local_stats["remaining"],
            percent_used=local_stats["percent_used"],
            deepl_character_count=deepl_stats.get("character_count"),
            deepl_character_limit=deepl_stats.get("character_limit"),
        ).model_dump(),
        "deepl": {
            "character_count": deepl_char_count,
            "character_limit": deepl_char_limit,
            "percent_used": round(deepl_percent, 2),
            "translate_count": deepl_stats.get("translate_count", 0),
            "write_count": deepl_stats.get("write_count", 0),
            "mock_mode": deepl_service.mock_mode,
            "error_message": deepl_service.get_error(),
        },
    }
