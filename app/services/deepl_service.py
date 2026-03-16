"""DeepL API service — singleton wrapper around the official deepl SDK."""

import asyncio
import logging
import time
from typing import Optional

import deepl

from app.config import settings

# Cache TTL for DeepL usage stats (seconds). Usage changes slowly; 60 s is sufficient.
_USAGE_CACHE_TTL = 60

logger = logging.getLogger(__name__)

# All DeepL target language codes that support a meaningful "intermediate"
# pivot for the double-translation style optimizer.
_LANG_INTERMEDIATE: dict[str, str] = {
    "DE": "EN-GB",
    "EN-GB": "DE",
    "EN-US": "DE",
    "FR": "DE",
    "ES": "DE",
    "IT": "DE",
    "NL": "DE",
    "PL": "DE",
    "PT-PT": "EN-GB",
    "PT-BR": "EN-GB",
    "RU": "EN-GB",
    "ZH": "EN-GB",
    "ZH-HANS": "EN-GB",
    "ZH-HANT": "EN-GB",
    "JA": "EN-GB",
    "KO": "EN-GB",
    "AR": "EN-GB",
    "BG": "DE",
    "CS": "DE",
    "DA": "DE",
    "EL": "EN-GB",
    "ET": "DE",
    "FI": "DE",
    "HU": "DE",
    "ID": "EN-GB",
    "LT": "DE",
    "LV": "DE",
    "NB": "DE",
    "RO": "DE",
    "SK": "DE",
    "SL": "DE",
    "SV": "DE",
    "TR": "EN-GB",
    "UK": "EN-GB",
}

# Map detected source-language codes to canonical target codes
_SOURCE_TO_TARGET: dict[str, str] = {
    "EN": "EN-GB",
    "PT": "PT-PT",
    "ZH": "ZH-HANS",
}


def _canonical_target(lang: str) -> str:
    """Normalise a detected source language code to a valid DeepL target code."""
    upper = lang.upper()
    return _SOURCE_TO_TARGET.get(upper, upper)


class DeepLService:
    """Thin wrapper around the DeepL SDK with mock-mode fallback."""

    def __init__(self) -> None:
        self._translator: Optional[deepl.Translator] = None
        self._mock_mode: bool = False
        self._error: Optional[str] = None
        # Usage cache — avoids a blocking HTTP call on every request
        self._usage_cache: Optional[dict] = None
        self._usage_cache_at: float = 0.0

        if not settings.deepl_api_key:
            self._mock_mode = True
            self._error = "DEEPL_API_KEY nicht gesetzt — Mock-Modus aktiv"
            logger.warning(self._error)
            return

        try:
            self._translator = deepl.Translator(
                settings.deepl_api_key.get_secret_value()
            )
            # Validate the key by fetching usage — raises if invalid
            self._translator.get_usage()
            logger.info("DeepL API erfolgreich initialisiert")
        except Exception as exc:
            self._mock_mode = True
            self._error = f"DeepL-Initialisierung fehlgeschlagen: {exc}"
            logger.error(self._error)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def is_configured(self) -> bool:
        return not self._mock_mode

    def get_error(self) -> Optional[str]:
        return self._error

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _empty_usage(self) -> dict:
        """Return a zeroed usage dict using the configured monthly limit."""
        return {
            "character_count": 0,
            "character_limit": settings.monthly_char_limit,
            "translate_count": 0,
            "write_count": 0,
        }

    @staticmethod
    def _get_detected_lang(result, fallback: str | None = None) -> str | None:
        """Extract and normalise detected_source_lang from a DeepL result object.

        Returns the detected language code (uppercase) or *fallback* if not available.
        """
        if hasattr(result, "detected_source_lang") and result.detected_source_lang:
            raw = str(result.detected_source_lang)
            return raw.upper() if raw else fallback
        return fallback

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: str = "DE",
    ) -> dict:
        """Translate *text* and return a dict with keys ``text`` and ``detected_source``."""
        if self._mock_mode:
            return {
                "text": f"[Mock {target_lang}] {text}",
                "detected_source": "EN",
                "billed_characters": len(text),
            }

        kwargs: dict = {"text": text, "target_lang": target_lang}
        if source_lang:
            kwargs["source_lang"] = source_lang

        try:
            result = self._translator.translate_text(**kwargs)
            detected = self._get_detected_lang(result)
            logger.debug(
                "DeepL translate: detected_source=%s target=%s", detected, target_lang
            )
            return {
                "text": result.text,
                "detected_source": detected,
                "billed_characters": getattr(result, "billed_characters", len(text)),
            }
        except Exception as exc:
            logger.error("DeepL Übersetzungsfehler: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Write / Style optimisation (double-translation)
    # ------------------------------------------------------------------

    def write_optimize(
        self,
        text: str,
        target_lang: str = "DE",
    ) -> dict:
        """Optimise *text* via a round-trip translation and return a dict with
        keys ``text`` and ``detected_lang``.

        The language detection is derived from the first translation result,
        so only **two** API calls are made (not three as before).

        Preserves paragraph breaks (double newlines) by using a placeholder
        during translation.
        """
        if self._mock_mode:
            return {
                "text": f"[Optimiert Mock] {text}",
                "detected_lang": target_lang,
                "billed_characters": len(text),
            }

        # Preserve paragraph breaks across the double-translation round-trip.
        #
        # Strategy: use DeepL's built-in XML tag handling (tag_handling="xml" +
        # ignore_tags=["p"]) so that paragraph markers are treated as protected
        # content and never translated or dropped.
        #
        # Previous attempts that failed:
        #   "|||PARAGRAPH|||" — DeepL translated "PARAGRAPH" → "ABSATZ" in DE
        #   "\r"              — DeepL silently strips carriage-return characters
        #   "<p/>"            — DeepL doesn't handle self-closing XML tags well
        #
        # Using <p></p> instead - DeepL's tag_handling="xml" works better with
        # opening/closing tag pairs than self-closing tags.
        PARAGRAPH_MARKER = "<p></p>"
        text_normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        text_for_translation = text_normalized.replace("\n\n", PARAGRAPH_MARKER)

        target_upper = target_lang.upper()
        intermediate = _LANG_INTERMEDIATE.get(target_upper, "EN-GB")

        # Shared DeepL kwargs for both translation steps
        _deepl_extra: dict = {
            "tag_handling": "xml",
            "ignore_tags": ["p"],
        }

        try:
            # Step 1: Translate to intermediate — auto-detects source language
            fwd_kwargs: dict = {
                "text": text_for_translation,
                "target_lang": intermediate,
                **_deepl_extra,
            }

            result1 = self._translator.translate_text(**fwd_kwargs)
            logger.debug(f"DeepL write_optimize result1: {repr(result1.text)}")
            # _get_detected_lang returns fallback when detection fails, so detected_raw is always str.
            detected_raw = self._get_detected_lang(result1, fallback=target_upper)
            detected = _canonical_target(detected_raw)

            # Step 2: Translate back to the detected original language
            bwd_kwargs: dict = {
                "text": result1.text,
                "target_lang": detected,
                **_deepl_extra,
            }

            result2 = self._translator.translate_text(**bwd_kwargs)

            # Restore paragraph breaks — <p/> is guaranteed to survive both steps
            result2.text = result2.text.replace(PARAGRAPH_MARKER, "\n\n")

            billed1 = getattr(result1, "billed_characters", len(text))
            billed2 = getattr(result2, "billed_characters", len(result1.text))

            logger.debug(
                "DeepL write_optimize: detected=%s intermediate=%s billed=%d",
                detected,
                intermediate,
                billed1 + billed2,
            )
            return {
                "text": result2.text,
                "detected_lang": detected,
                "billed_characters": billed1 + billed2,
            }

        except Exception as exc:
            logger.error("DeepL Optimierungsfehler: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Usage statistics
    # ------------------------------------------------------------------

    def get_usage(self) -> dict:
        """Return DeepL API usage statistics (synchronous, with 60 s cache).

        Returns a dict with:
          - ``character_count``  — characters used this billing period
          - ``character_limit``  — monthly character limit
          - ``translate_count``  — characters used for translation (if available)
          - ``write_count``      — characters used for write/optimise (if available)

        Results are cached for ``_USAGE_CACHE_TTL`` seconds to avoid blocking
        the event loop on every request. On failure, a fallback response is
        cached for 30 s to prevent hammering a failing API under sustained outage.
        Use ``async_get_usage()`` from async contexts to avoid blocking entirely.
        """
        if self._mock_mode:
            return self._empty_usage()

        now = time.monotonic()
        if (
            self._usage_cache is not None
            and (now - self._usage_cache_at) < _USAGE_CACHE_TTL
        ):
            return self._usage_cache

        try:
            usage = self._translator.get_usage()

            # The DeepL SDK exposes usage.character (a Usage.Detail object)
            # with .count and .limit attributes.
            char_detail = getattr(usage, "character", None)
            if char_detail is not None:
                character_count = getattr(char_detail, "count", 0) or 0
                character_limit = (
                    getattr(char_detail, "limit", settings.monthly_char_limit)
                    or settings.monthly_char_limit
                )
            else:
                # Older SDK versions may expose flat attributes
                character_count = int(getattr(usage, "character_count", 0) or 0)
                character_limit = int(
                    getattr(usage, "character_limit", settings.monthly_char_limit)
                    or settings.monthly_char_limit
                )

            translate_count = 0
            write_count = 0

            # Pro accounts expose per-product breakdown
            products = getattr(usage, "products", None)
            if products:
                for product in products:
                    ptype = getattr(product, "product_type", "")
                    pcount = getattr(product, "character_count", 0) or 0
                    if ptype == "translate":
                        translate_count = int(pcount)
                    elif ptype == "write":
                        write_count = int(pcount)

            result = {
                "character_count": character_count,
                "character_limit": character_limit,
                "translate_count": translate_count,
                "write_count": write_count,
            }
            self._usage_cache = result
            self._usage_cache_at = now
            return result

        except Exception as exc:
            logger.error("DeepL Usage-Abfrage fehlgeschlagen: %s", exc)
            fallback = self._empty_usage()
            # Cache the fallback for 30 s to avoid hammering a failing API under
            # sustained outage. This balances quick recovery against not hammering
            # a downed DeepL API with every active user's first request.
            self._usage_cache = fallback
            self._usage_cache_at = now - (_USAGE_CACHE_TTL - 30)
            return fallback

    async def async_get_usage(self) -> dict:
        """Async wrapper around ``get_usage()`` — offloads it to a thread pool.

        Returns the cached result immediately if the cache is still fresh;
        otherwise runs the blocking DeepL SDK call off the event loop.
        Use this from async route handlers to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self.get_usage)


# Module-level singleton — instantiated once at import time
deepl_service = DeepLService()
