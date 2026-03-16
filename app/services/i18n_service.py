"""i18n service for loading and serving translations."""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Supported UI languages
SUPPORTED_LANGUAGES = [
    {"code": "en", "name": "English", "native_name": "English"},
    {"code": "de", "name": "German", "native_name": "Deutsch"},
    {"code": "fr", "name": "French", "native_name": "Français"},
    {"code": "it", "name": "Italian", "native_name": "Italiano"},
    {"code": "es", "name": "Spanish", "native_name": "Español"},
]

DEFAULT_LANGUAGE = "en"

# Cache for loaded translations
_translations_cache: dict[str, dict[str, str]] = {}


def _get_i18n_dir() -> Path:
    """Return the path to the i18n directory."""
    # Base directory is two levels up from app/
    base_dir = Path(__file__).parent.parent.parent
    return base_dir / "static" / "i18n"


def get_translations(lang: str) -> dict[str, str]:
    """Get all translations for a given language code.

    Falls back to English if the requested language is not available.
    """
    # Normalize language code (e.g., "en-US" -> "en")
    lang_code = lang.split("-")[0].lower() if lang else DEFAULT_LANGUAGE

    # Check cache first
    if lang_code in _translations_cache:
        return _translations_cache[lang_code]

    i18n_dir = _get_i18n_dir()
    translation_file = i18n_dir / f"{lang_code}.json"

    # Try to load the translation file
    translations: dict[str, str] = {}

    if translation_file.exists():
        try:
            with open(translation_file, "r", encoding="utf-8") as f:
                raw_translations = json.load(f)
                # Flatten nested structure to dot notation
                translations = _flatten_dict(raw_translations)
                logger.info("Loaded translations for language: %s", lang_code)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to load translations for %s: %s", lang_code, exc)

    # Fall back to English if not found or failed to load
    if lang_code != DEFAULT_LANGUAGE and not translations:
        translations = get_translations(DEFAULT_LANGUAGE)

    # Cache the result
    _translations_cache[lang_code] = translations
    return translations


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, str]:
    """Flatten a nested dictionary to dot-notation keys."""
    items: list[tuple[str, str]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, str(v)))
    return dict(items)


def get_supported_languages() -> list[dict]:
    """Return list of supported UI languages with localized names."""
    return SUPPORTED_LANGUAGES


def get_default_language() -> str:
    """Return the default language code."""
    return DEFAULT_LANGUAGE


def get_language_name(lang: str, in_language: Optional[str] = None) -> str:
    """Get the name of a language.

    If in_language is provided, returns the name in that language.
    Otherwise returns the native name.
    """
    lang_code = lang.split("-")[0].lower() if lang else DEFAULT_LANGUAGE

    for lang_info in SUPPORTED_LANGUAGES:
        if lang_info["code"] == lang_code:
            if in_language:
                translations = get_translations(in_language)
                key = f"languages.{lang_code.upper()}"
                return translations.get(key, lang_info["native_name"])
            return lang_info["native_name"]

    return lang


def is_supported(lang: str) -> bool:
    """Check if a language code is supported."""
    lang_code = lang.split("-")[0].lower() if lang else ""
    return any(lang_info["code"] == lang_code for lang_info in SUPPORTED_LANGUAGES)
