"""Tests for the i18n service."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.services.i18n_service import (
    get_translations,
    get_supported_languages,
    get_default_language,
    get_language_name,
    is_supported,
    _flatten_dict,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)


class TestFlattenDict:
    """Tests for _flatten_dict helper."""

    def test_flatten_simple_dict(self):
        """Flatten a simple nested dictionary."""
        d = {"a": "1", "b": "2"}
        result = _flatten_dict(d)
        assert result == {"a": "1", "b": "2"}

    def test_flatten_nested_dict(self):
        """Flatten a nested dictionary to dot notation."""
        d = {"nav": {"translate": "Translate", "write": "Write"}}
        result = _flatten_dict(d)
        assert result == {"nav.translate": "Translate", "nav.write": "Write"}

    def test_flatten_deeply_nested(self):
        """Flatten a deeply nested dictionary."""
        d = {"a": {"b": {"c": "value"}}}
        result = _flatten_dict(d)
        assert result == {"a.b.c": "value"}

    def test_flatten_with_numbers(self):
        """Flatten handles numeric values by converting to string."""
        d = {"count": 42, "nested": {"score": 100}}
        result = _flatten_dict(d)
        assert result == {"count": "42", "nested.score": "100"}


class TestGetSupportedLanguages:
    """Tests for get_supported_languages()."""

    def test_returns_all_supported_languages(self):
        """Returns the full list of supported languages."""
        result = get_supported_languages()
        assert len(result) == 5
        codes = [lang["code"] for lang in result]
        assert "en" in codes
        assert "de" in codes
        assert "fr" in codes
        assert "it" in codes
        assert "es" in codes

    def test_language_has_required_fields(self):
        """Each language has code, name, and native_name."""
        for lang in get_supported_languages():
            assert "code" in lang
            assert "name" in lang
            assert "native_name" in lang


class TestGetDefaultLanguage:
    """Tests for get_default_language()."""

    def test_returns_english(self):
        """Default language should be English."""
        assert get_default_language() == "en"


class TestIsSupported:
    """Tests for is_supported()."""

    def test_supports_english(self):
        """English is supported."""
        assert is_supported("en") is True
        assert is_supported("EN") is True
        assert is_supported("en-US") is True

    def test_supports_german(self):
        """German is supported."""
        assert is_supported("de") is True
        assert is_supported("DE") is True
        assert is_supported("de-DE") is True

    def test_supports_french(self):
        """French is supported."""
        assert is_supported("fr") is True

    def test_supports_italian(self):
        """Italian is supported."""
        assert is_supported("it") is True

    def test_supports_spanish(self):
        """Spanish is supported."""
        assert is_supported("es") is True

    def test_rejects_unsupported(self):
        """Unsupported languages return False."""
        assert is_supported("zh") is False
        assert is_supported("ja") is False
        assert is_supported("ru") is False
        assert is_supported("xx") is False

    def test_handles_empty_input(self):
        """Empty input returns False."""
        assert is_supported("") is False


class TestGetLanguageName:
    """Tests for get_language_name()."""

    def test_returns_native_name_by_default(self):
        """Returns native name when no in_language specified."""
        assert get_language_name("de") == "Deutsch"
        assert get_language_name("fr") == "Français"
        assert get_language_name("it") == "Italiano"
        assert get_language_name("es") == "Español"

    def test_handles_unknown_language(self):
        """Unknown language code returns the input unchanged."""
        assert get_language_name("xyz") == "xyz"

    def test_handles_empty_input(self):
        """Empty input returns default language."""
        result = get_language_name("")
        assert result == "English"  # Returns native name of default language

    def test_handles_region_code(self):
        """Handles region codes like en-US."""
        assert get_language_name("en-US") == "English"


class TestGetTranslations:
    """Tests for get_translations()."""

    def test_loads_english_translations(self):
        """Loads English translations from JSON file."""
        # Clear cache to force reload
        from app.services import i18n_service

        i18n_service._translations_cache.clear()

        result = get_translations("en")
        assert isinstance(result, dict)
        # English translations should contain known keys
        assert "nav.translate" in result
        assert "nav.write" in result

    def test_normalizes_language_code(self):
        """Normalizes language codes like en-US to en."""
        # Clear cache
        from app.services import i18n_service

        i18n_service._translations_cache.clear()

        result_en = get_translations("en")
        result_en_us = get_translations("en-US")
        # Both should work and return translations
        assert isinstance(result_en, dict)
        assert isinstance(result_en_us, dict)

    def test_falls_back_to_english(self):
        """Falls back to English for unsupported languages."""
        # Clear cache
        from app.services import i18n_service

        i18n_service._translations_cache.clear()

        result = get_translations("xyz")
        # Should return English fallback
        assert isinstance(result, dict)
        # English translations should contain known keys
        assert "nav.translate" in result

    def test_caches_results(self):
        """Results are cached for subsequent calls."""
        # First call loads from disk
        result1 = get_translations("en")
        # Second call should use cache
        result2 = get_translations("en")
        assert result1 is result2
