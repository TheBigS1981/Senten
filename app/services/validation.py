"""Input validation service for LLM endpoints.

Provides pattern-based detection of prompt injection attempts and other
malicious input targeting LLM endpoints. Language-code validation is
handled separately by _validate_llm_languages() in the translate router.

Design principles:
- Allowlist approach: valid translation/writing text should pass through.
- Blocklist approach only for clear injection patterns (jailbreak attempts,
  system prompt overrides, role-play escape patterns).
- False positives are worse than false negatives here: we don't want to
  block legitimate text that coincidentally looks like an instruction.
- Keep it simple: regex over ML — no external dependencies.
"""

import logging
import re

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection pattern catalog
# ---------------------------------------------------------------------------
# Each entry is (pattern, description) — description is for logging only.
# Patterns are matched case-insensitively against the full input text.
#
# Design rationale:
# - We target STRUCTURAL injection markers, not semantic intent.
#   "Ignore the previous instructions" in German literary text is fine.
#   But starting a message with that phrase as the first meaningful content
#   after whitespace signals an injection attempt.
# - We do NOT block any normal translation/writing content.
# - All patterns are anchored or require specific structural context.

_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── System prompt overrides ────────────────────────────────────────────
    (
        re.compile(
            r"(?:^|\n)\s*(?:ignore|forget|disregard|override)\s+"
            r"(?:all\s+)?(?:previous|prior|above|earlier|your)\s+"
            r"(?:instructions?|prompt|context|directives?|system)",
            re.IGNORECASE,
        ),
        "system prompt override attempt",
    ),
    (
        re.compile(
            r"(?:^|\n)\s*(?:new\s+)?system\s+prompt\s*:",
            re.IGNORECASE,
        ),
        "inline system prompt injection",
    ),
    (
        re.compile(
            r"(?:^|\n)\s*\[(?:SYSTEM|INST|SYS|CONTEXT|OVERRIDE)\]",
            re.IGNORECASE,
        ),
        "bracket-delimited system tag injection",
    ),
    # ── Role-play escape patterns ──────────────────────────────────────────
    (
        re.compile(
            r"(?:^|\n)\s*(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|"
            r"roleplay\s+as|play\s+the\s+role\s+of)\s+"
            # Negative lookahead: allow professional/occupational contexts
            # (translator, editor, writer, interpreter, assistant, proofreader)
            r"(?!(?:a\s+)?(?:professional\s+)?(?:translator|editor|writer|interpreter|assistant|proofreader))",
            re.IGNORECASE,
        ),
        "role-play escape attempt",
    ),
    # ── DAN / jailbreak templates ──────────────────────────────────────────
    (
        re.compile(
            r"\bDAN\b.*\bhave\s+no\s+(?:restrictions?|limits?|filters?)\b",
            re.IGNORECASE,
        ),
        "DAN jailbreak pattern",
    ),
    (
        re.compile(
            r"\bdo\s+anything\s+now\b",
            re.IGNORECASE,
        ),
        "DAN 'do anything now' pattern",
    ),
    # ── Prompt delimiter injection ─────────────────────────────────────────
    # These are structural markers used in LLM training/inference formats.
    # Legitimate translation text does not contain these raw tokens.
    (
        re.compile(
            r"<\|(?:im_start|im_end|system|user|assistant|endoftext)\|>",
            re.IGNORECASE,
        ),
        "ChatML / special token injection",
    ),
    (
        re.compile(
            r"\[/?(?:INST|SYS)\]",
            re.IGNORECASE,
        ),
        "Llama instruction token injection",
    ),
    # ── Output exfiltration attempts ───────────────────────────────────────
    (
        re.compile(
            r"(?:^|\n)\s*(?:print|echo|output|reveal|show|display|return|leak)\s+"
            r"(?:your\s+)?(?:system\s+prompt|instructions?|context|api\s+key|secret)",
            re.IGNORECASE,
        ),
        "system context exfiltration attempt",
    ),
]

# Maximum input length for LLM endpoints (characters).
# The hard limit is enforced by LLM_MAX_INPUT_CHARS in config.
# This check here is a belt-and-suspenders guard at the validation layer.
_MAX_INPUT_CHARS = 50_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_llm_input(text: str, endpoint: str = "llm") -> None:
    """Validate user input destined for an LLM endpoint.

    Raises HTTPException(422) if a prompt injection pattern is detected.
    Raises HTTPException(413) if the text is excessively long.

    Args:
        text: The user-supplied input text (already stripped).
        endpoint: Label for log messages (e.g. "translate", "write").
    """
    if len(text) > _MAX_INPUT_CHARS:
        logger.warning(
            "validate_llm_input: input too long (%d chars) for endpoint=%s",
            len(text),
            endpoint,
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Text zu lang (max. {_MAX_INPUT_CHARS:,} Zeichen).",
        )

    for pattern, description in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "validate_llm_input: injection pattern detected [%s] for endpoint=%s",
                description,
                endpoint,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Ungültige Eingabe.",
            )
