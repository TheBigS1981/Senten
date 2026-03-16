"""Translation and write/optimise API endpoints."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import deepl.exceptions
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.limiter import limiter
from app.models.schemas import (
    DEEPL_SOURCE_LANGUAGES,
    DEEPL_TARGET_LANGUAGES,
    DetectLangRequest,
    DetectLangResponse,
    TranslateRequest,
    TranslateResponse,
    WriteRequest,
    WriteResponse,
)
from app.services.deepl_service import deepl_service
from app.services.llm_service import (
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMModelError,
    LLMQuotaError,
    LLMTimeoutError,
    llm_service,
)
from app.services.usage_service import usage_service
from app.services.validation import validate_llm_input
from app.utils import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _record_usage(
    user_id: str,
    text: str,
    operation_type: str,
    target_language: str,
    double_characters: bool = False,
    billed_characters: int | None = None,
    word_count: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> int:
    """Record usage and return character count used.

    If *billed_characters* is provided (from the DeepL SDK result), it takes
    precedence over the local estimation based on ``len(text)``.  This ensures
    that the recorded count matches what DeepL actually billed.
    """
    if billed_characters is not None:
        chars_used = billed_characters
    else:
        chars_used = len(text) * (2 if double_characters else 1)
    usage_service.record_usage(
        user_id=user_id,
        characters=chars_used,
        operation_type=operation_type,
        target_language=target_language,
        word_count=word_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return chars_used


# Maps specific LLM exception types to (HTTP status code, error code, user-facing message).
# Checked in order — more specific subclasses must come before LLMError.
_LLM_ERROR_MAP: list[tuple[type, int, str]] = [
    (
        LLMTimeoutError,
        status.HTTP_408_REQUEST_TIMEOUT,
        "ERR_LLM_TIMEOUT",
    ),
    (
        LLMAuthError,
        status.HTTP_401_UNAUTHORIZED,
        "ERR_LLM_AUTH",
    ),
    (
        LLMQuotaError,
        status.HTTP_429_TOO_MANY_REQUESTS,
        "ERR_LLM_QUOTA",
    ),
    (
        LLMModelError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "ERR_LLM_MODEL",
    ),
    (
        LLMConnectionError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "ERR_LLM_CONNECTION",
    ),
]


def _handle_llm_error(exc: Exception, user_id: str, operation: str) -> HTTPException:
    """Log LLM error and return a specific HTTP exception based on the error type."""
    logger.error("LLM %s-Fehler für user=%s: %s", operation, user_id, exc)

    for exc_type, http_status, error_code in _LLM_ERROR_MAP:
        if isinstance(exc, exc_type):
            return HTTPException(status_code=http_status, detail=error_code)

    if isinstance(exc, LLMError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ERR_TRANSLATE_FAILED"
            if operation == "Übersetzung"
            else "ERR_WRITE_FAILED",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ERR_TRANSLATE_FAILED"
        if operation == "Übersetzung"
        else "ERR_WRITE_FAILED",
    )


# Maps specific DeepL exception types to (log level, HTTP status, error code).
# Checked in order — more specific subclasses must come before DeepLException.
_DEEPL_ERROR_MAP: list[tuple[type, int, int, str | None]] = [
    (
        deepl.exceptions.TooManyRequestsException,
        logging.WARNING,
        status.HTTP_429_TOO_MANY_REQUESTS,
        "ERR_DEEPL_RATE_LIMIT",
    ),
    (
        deepl.exceptions.QuotaExceededException,
        logging.WARNING,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "ERR_DEEPL_QUOTA",
    ),
    (
        deepl.exceptions.AuthorizationException,
        logging.ERROR,
        status.HTTP_401_UNAUTHORIZED,
        "ERR_DEEPL_AUTH",
    ),
    (
        deepl.exceptions.DeepLException,
        logging.ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        None,  # detail is operation-specific; filled in below
    ),
]


def _handle_deepl_error(exc: Exception, user_id: str, operation: str) -> HTTPException:
    """Log a DeepL error and return the appropriate HTTP exception."""
    for exc_type, log_level, http_status, error_code in _DEEPL_ERROR_MAP:
        if isinstance(exc, exc_type):
            logger.log(
                log_level,
                "DeepL %s bei %s für user=%s: %s",
                exc_type.__name__,
                operation,
                user_id,
                exc,
            )
            return HTTPException(
                status_code=http_status,
                detail=error_code
                or (
                    "ERR_TRANSLATE_FAILED"
                    if operation == "Übersetzung"
                    else "ERR_WRITE_FAILED"
                ),
            )
    logger.error("Unerwarteter Fehler bei %s für user=%s: %s", operation, user_id, exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ERR_TRANSLATE_FAILED"
        if operation == "Übersetzung"
        else "ERR_WRITE_FAILED",
    )


def _validate_llm_languages(
    target_lang: str,
    source_lang: str | None = None,
) -> None:
    """Raise HTTPException if any language code is not in the canonical DeepL lists.

    ``target_lang`` is required; ``source_lang`` is optional (skipped when None).
    Validates against the official DeepL language lists to prevent prompt-injection
    attacks where arbitrary strings are passed as language names to the LLM.
    """
    if target_lang not in DEEPL_TARGET_LANGUAGES:
        logger.warning("Ungültige Zielsprache angefordert: %r", target_lang)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ERR_INVALID_TARGET_LANG",
        )
    if source_lang and source_lang not in DEEPL_SOURCE_LANGUAGES:
        logger.warning("Ungültige Quellsprache angefordert: %r", source_lang)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ERR_INVALID_SOURCE_LANG",
        )


def _extract_token_usage(usage_data: dict) -> tuple[int, int]:
    """Extract input/output token counts from a usage dict returned by LLM routes."""
    if not isinstance(usage_data, dict):
        return 0, 0
    return int(usage_data.get("input_tokens", 0)), int(
        usage_data.get("output_tokens", 0)
    )


def _validate_llm_request(
    text: str,
    target_lang: str,
    source_lang: str | None,
    endpoint_name: str,
) -> None:
    """Run the standard 4-step guard for all LLM route handlers.

    Raises HTTPException on the first failing check:
      1. LLM not configured → 503
      2. Text too long → 413
      3. Invalid language code → 422
      4. Prompt injection → 422
    """
    if not llm_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERR_LLM_NOT_CONFIGURED",
        )
    if len(text) > settings.llm_max_input_chars:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="ERR_TEXT_TOO_LONG",
        )
    _validate_llm_languages(target_lang, source_lang)
    validate_llm_input(text, endpoint=endpoint_name)


async def _stream_with_usage(
    gen: AsyncGenerator,
    user_id: str,
    text: str,
    op_type: str,
    target_lang: str,
) -> AsyncGenerator:
    """Wrap an SSE generator and record usage only after successful completion.

    Usage is debited only when the stream emits a ``done`` event, ensuring
    that failed or client-aborted streams do not consume the character budget.

    Each SSE chunk has the form ``data: <json>\\n\\n``.  We parse the JSON to
    detect the done event precisely, rather than relying on substring matching
    which could trigger early if the translated text itself contains '"done"'.

    Token counts (input_tokens, output_tokens) are extracted from the done event
    when the LLM provider includes them (OpenAI, Anthropic). Ollama yields 0.
    """
    done_seen = False
    input_tokens = 0
    output_tokens = 0
    async for chunk in gen:
        yield chunk
        for line in chunk.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
                if event.get("done") is True:
                    done_seen = True
                    input_tokens = int(event.get("input_tokens", 0))
                    output_tokens = int(event.get("output_tokens", 0))
            except (json.JSONDecodeError, AttributeError, ValueError):
                pass
    if done_seen:
        _record_usage(
            user_id,
            text,
            op_type,
            target_lang,
            word_count=len(text.split()),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Configuration endpoint
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_config():
    """Return DeepL and LLM configuration status plus language options."""
    llm_active = llm_service.is_configured()
    return {
        "configured": deepl_service.is_configured(),
        "mock_mode": deepl_service.mock_mode,
        "error": deepl_service.get_error(),
        "llm_configured": llm_active,
        "llm_provider": llm_service.provider_name if llm_active else None,
        "llm_display_name": llm_service.display_name if llm_active else None,
        "llm_translate_model": llm_service.translate_model if llm_active else None,
        "llm_write_model": llm_service.write_model if llm_active else None,
        "llm_max_input_chars": settings.llm_max_input_chars,
        "languages": {
            "targets": DEEPL_TARGET_LANGUAGES,
            "sources": DEEPL_SOURCE_LANGUAGES,
        },
    }


# ---------------------------------------------------------------------------
# Translate
# ---------------------------------------------------------------------------


@router.post("/translate", response_model=TranslateResponse)
@limiter.limit("30/minute")
async def translate_text(request: Request, body: TranslateRequest):
    """Translate text using DeepL or LLM depending on the engine field."""
    user_id = get_user_id(request)
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_TEXT_EMPTY",
        )

    # ── LLM Engine ──────────────────────────────────────────────────────────
    if body.engine == "llm":
        _validate_llm_request(text, body.target_lang, body.source_lang, "translate")
        try:
            result = await llm_service.translate(
                text=text,
                target_lang=body.target_lang,
                source_lang=body.source_lang or None,
            )
        except Exception as exc:
            raise _handle_llm_error(exc, user_id, "Übersetzung")

        usage_data = result.get("usage") or {}
        input_tok, output_tok = _extract_token_usage(usage_data)
        chars_used = _record_usage(
            user_id,
            text,
            "translate",
            body.target_lang,
            word_count=len(text.split()),
            input_tokens=input_tok,
            output_tokens=output_tok,
        )
        response_data = {
            "translated_text": result["translated_text"],
            "detected_source_lang": result.get("detected_source_lang"),
            "characters_used": chars_used,
        }
        if (
            usage_data
            and isinstance(usage_data, dict)
            and all(isinstance(v, int) for v in usage_data.values())
        ):
            response_data["usage"] = usage_data
        return TranslateResponse(**response_data)

    # ── DeepL Engine (default) ───────────────────────────────────────────────
    try:
        result = await asyncio.to_thread(
            deepl_service.translate,
            text=text,
            source_lang=body.source_lang or None,
            target_lang=body.target_lang,
        )
    except Exception as exc:
        raise _handle_deepl_error(exc, user_id, "Übersetzung")

    chars_used = _record_usage(
        user_id,
        text,
        "translate",
        body.target_lang,
        billed_characters=result.get("billed_characters"),
        word_count=len(text.split()),
    )

    return TranslateResponse(
        translated_text=result["text"],
        detected_source_lang=result.get("detected_source"),
        characters_used=chars_used,
    )


# ---------------------------------------------------------------------------
# Write / Style optimisation
# ---------------------------------------------------------------------------


@router.post("/write", response_model=WriteResponse)
@limiter.limit("30/minute")
async def write_optimize(request: Request, body: WriteRequest):
    """Optimise and rephrase text via DeepL double-translation or LLM."""
    user_id = get_user_id(request)
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_TEXT_EMPTY",
        )

    # ── LLM Engine ──────────────────────────────────────────────────────────
    if body.engine == "llm":
        _validate_llm_request(text, body.target_lang, None, "write")
        try:
            result = await llm_service.write_optimize(
                text=text,
                target_lang=body.target_lang,
            )
        except Exception as exc:
            raise _handle_llm_error(exc, user_id, "Optimierung")

        usage_data = result.get("usage") or {}
        input_tok, output_tok = _extract_token_usage(usage_data)
        chars_used = _record_usage(
            user_id,
            text,
            "write",
            body.target_lang,
            word_count=len(text.split()),
            input_tokens=input_tok,
            output_tokens=output_tok,
        )
        response_data = {
            "optimized_text": result["optimized_text"],
            "characters_used": chars_used,
        }
        if (
            usage_data
            and isinstance(usage_data, dict)
            and all(isinstance(v, int) for v in usage_data.values())
        ):
            response_data["usage"] = usage_data
        return WriteResponse(**response_data)

    # ── DeepL Engine (default) ───────────────────────────────────────────────
    try:
        result = await asyncio.to_thread(
            deepl_service.write_optimize,
            text=text,
            target_lang=body.target_lang,
        )
    except Exception as exc:
        raise _handle_deepl_error(exc, user_id, "Optimierung")

    chars_used = _record_usage(
        user_id,
        text,
        "write",
        body.target_lang,
        billed_characters=result.get("billed_characters"),
        word_count=len(text.split()),
    )

    return WriteResponse(
        optimized_text=result["text"],
        characters_used=chars_used,
    )


# ---------------------------------------------------------------------------
# LLM Streaming endpoints
# ---------------------------------------------------------------------------


@router.post("/translate/stream")
@limiter.limit("30/minute")
async def translate_stream(request: Request, body: TranslateRequest):
    """Stream LLM translation as Server-Sent Events.

    Only available when engine='llm'. Falls back to a 400 error for DeepL
    (DeepL has no streaming API).

    SSE event format:
      data: {"chunk": "<text>"}      — incremental translation chunk
      data: {"done": true, "detected_source_lang": "<code>"}  — final event
      data: {"error": "<message>"}   — on error (stream terminates after this)
    """
    user_id = get_user_id(request)
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_TEXT_EMPTY",
        )

    if body.engine != "llm":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_STREAMING_LLM_ONLY",
        )

    _validate_llm_request(text, body.target_lang, body.source_lang, "translate/stream")

    return StreamingResponse(
        _stream_with_usage(
            llm_service.translate_stream(
                text=text,
                target_lang=body.target_lang,
                source_lang=body.source_lang or None,
            ),
            user_id=user_id,
            text=text,
            op_type="translate",
            target_lang=body.target_lang,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/write/stream")
@limiter.limit("30/minute")
async def write_stream(request: Request, body: WriteRequest):
    """Stream LLM write/optimise as Server-Sent Events.

    Only available when engine='llm'.

    SSE event format:
      data: {"chunk": "<text>"}   — incremental optimised chunk
      data: {"done": true}        — final event
      data: {"error": "<message>"}— on error
    """
    user_id = get_user_id(request)
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_TEXT_EMPTY",
        )

    if body.engine != "llm":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_STREAMING_LLM_ONLY",
        )

    _validate_llm_request(text, body.target_lang, None, "write/stream")

    return StreamingResponse(
        _stream_with_usage(
            llm_service.write_optimize_stream(
                text=text,
                target_lang=body.target_lang,
            ),
            user_id=user_id,
            text=text,
            op_type="write",
            target_lang=body.target_lang,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Language detection endpoint
# ---------------------------------------------------------------------------


@router.post("/detect-lang", response_model=DetectLangResponse)
@limiter.limit(
    "60/minute"
)  # Higher than other LLM endpoints: called before every stream
async def detect_language(request: Request, body: DetectLangRequest):
    """Detect the language of a short text snippet via LLM.

    Designed to be called *before* starting a streaming translation so the
    correct target language is known upfront. Returns {"detected_lang": "unknown"}
    on any failure — never raises 5xx — so the caller can fall back gracefully.
    """
    text = body.text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ERR_TEXT_EMPTY",
        )

    if not llm_service.is_configured():
        return DetectLangResponse(detected_lang="unknown")

    # Validate input for injection patterns — consistent with all other LLM endpoints.
    # On injection: raise 422 immediately (do not degrade gracefully — caller should handle).
    validate_llm_input(text, endpoint="detect-lang")

    try:
        detected = await llm_service.detect_language(text, max_words=body.max_words)
        return DetectLangResponse(detected_lang=detected or "unknown")
    except Exception as exc:
        logger.warning("detect-lang endpoint: detection failed: %s", exc)
        return DetectLangResponse(detected_lang="unknown")
