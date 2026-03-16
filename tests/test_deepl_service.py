"""Unit tests for the DeepL service.

Tests the DeepLService class including mock mode, translate, write_optimize,
and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.deepl_service import DeepLService


class TestDeepLServiceMockMode:
    """Tests for DeepL service mock mode (no API key configured)."""

    @pytest.fixture
    def mock_service(self, monkeypatch):
        """Create a DeepLService instance in mock mode."""
        # Force mock mode by clearing API key
        monkeypatch.setenv("DEEPL_API_KEY", "")

        # Reload the config to pick up the new env var
        import importlib

        import app.config

        importlib.reload(app.config)

        # Reload the deepl_service module to get fresh instance
        import app.services.deepl_service as deepl_module

        importlib.reload(deepl_module)

        return deepl_module.deepl_service

    def test_mock_mode_is_active(self, mock_service):
        """Service should be in mock mode when no API key is set."""
        assert mock_service.mock_mode is True

    def test_is_configured_returns_false_in_mock_mode(self, mock_service):
        """is_configured should return False in mock mode."""
        assert mock_service.is_configured() is False

    def test_get_error_returns_message_in_mock_mode(self, mock_service):
        """get_error should return a descriptive message in mock mode."""
        error = mock_service.get_error()
        assert error is not None
        assert "DEEPL_API_KEY" in error

    def test_translate_in_mock_mode_returns_mock_text(self, mock_service):
        """translate() should return mock text in mock mode."""
        result = mock_service.translate("Hello world", target_lang="DE")

        assert "text" in result
        assert "detected_source" in result
        assert "[Mock DE]" in result["text"]
        assert result["detected_source"] == "EN"

    def test_translate_mock_preserves_input(self, mock_service):
        """translate() in mock mode should preserve the input text."""
        result = mock_service.translate("Original text here", target_lang="FR")

        assert "Original text here" in result["text"]
        assert "[Mock FR]" in result["text"]

    def test_write_optimize_in_mock_mode_returns_mock_text(self, mock_service):
        """write_optimize() should return mock text in mock mode."""
        result = mock_service.write_optimize("Some text to optimize", target_lang="DE")

        assert "text" in result
        assert "detected_lang" in result
        assert "[Optimiert Mock]" in result["text"]
        assert result["detected_lang"] == "DE"

    def test_get_usage_in_mock_mode_returns_zeros(self, mock_service):
        """get_usage() should return zeros in mock mode."""
        result = mock_service.get_usage()

        assert result["character_count"] == 0
        assert result["translate_count"] == 0
        assert result["write_count"] == 0
        assert result["character_limit"] > 0


class TestDeepLServiceWithMockTranslator:
    """Tests for DeepL service with a mocked translator (API key present but mocked)."""

    @pytest.fixture
    def service_with_mock(self, monkeypatch):
        """Create a DeepLService with a mocked translator."""
        # Set an API key (but we'll mock the translator)
        monkeypatch.setenv("DEEPL_API_KEY", "test-api-key-for-mocking")

        import importlib

        import app.config

        importlib.reload(app.config)

        import app.services.deepl_service as deepl_module

        importlib.reload(deepl_module)

        return deepl_module.DeepLService()

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_calls_api(self, mock_translator_cls, service_with_mock):
        """translate() should call the DeepL API."""
        # Set up mock translator
        mock_translator = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Übersetzter Text"
        mock_result.detected_source_lang = "EN"
        mock_translator.translate_text.return_value = mock_result

        mock_translator_cls.return_value = mock_translator

        # Create fresh service with mocked translator
        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.translate("Original text", target_lang="DE")

        assert result["text"] == "Übersetzter Text"
        assert result["detected_source"] == "EN"
        mock_translator.translate_text.assert_called_once()

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_without_formality(self, mock_translator_cls, service_with_mock):
        """translate() should not pass formality to the API (feature removed)."""
        mock_translator = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Text"
        mock_result.detected_source_lang = "EN"
        mock_translator.translate_text.return_value = mock_result

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        service.translate("Hello", target_lang="DE")

        # Formality should not be passed to the API
        call_kwargs = mock_translator.translate_text.call_args.kwargs
        assert "formality" not in call_kwargs

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_with_source_lang(self, mock_translator_cls, service_with_mock):
        """translate() should pass source_lang to API when provided."""
        mock_translator = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Text"
        mock_result.detected_source_lang = "DE"
        mock_translator.translate_text.return_value = mock_result

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        service.translate("Hallo", source_lang="DE", target_lang="EN-GB")

        call_kwargs = mock_translator.translate_text.call_args.kwargs
        assert call_kwargs.get("source_lang") == "DE"

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_error_raises_exception(
        self, mock_translator_cls, service_with_mock
    ):
        """translate() should raise an exception on API error."""
        mock_translator = MagicMock()
        mock_translator.translate_text.side_effect = Exception("API Error")

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        with pytest.raises(Exception) as exc_info:
            service.translate("test", target_lang="DE")

        assert "API Error" in str(exc_info.value)

    @patch("app.services.deepl_service.deepl.Translator")
    def test_write_optimize_makes_two_api_calls(
        self, mock_translator_cls, service_with_mock
    ):
        """write_optimize() should make two API calls (double translation)."""
        mock_translator = MagicMock()

        # First call result (forward translation)
        mock_result1 = MagicMock()
        mock_result1.text = "Translated to intermediate"
        mock_result1.detected_source_lang = "EN"

        # Second call result (back translation)
        mock_result2 = MagicMock()
        mock_result2.text = "Optimized text"

        mock_translator.translate_text.side_effect = [mock_result1, mock_result2]

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.write_optimize("Original text", target_lang="DE")

        # Should have been called twice
        assert mock_translator.translate_text.call_count == 2
        assert result["text"] == "Optimized text"

    @patch("app.services.deepl_service.deepl.Translator")
    def test_write_optimize_detects_language_from_first_result(
        self, mock_translator_cls
    ):
        """write_optimize() should detect language from first translation result."""
        mock_translator = MagicMock()

        mock_result1 = MagicMock()
        mock_result1.text = "Zwischentext"
        mock_result1.detected_source_lang = "EN"  # Detected as English

        mock_result2 = MagicMock()
        mock_result2.text = "Optimized English text"

        mock_translator.translate_text.side_effect = [mock_result1, mock_result2]

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        service.write_optimize("Original text", target_lang="DE")

        # The second call should target the detected language (EN)
        second_call_kwargs = mock_translator.translate_text.call_args_list[1].kwargs
        assert second_call_kwargs["target_lang"] == "EN-GB"  # Canonical form

    @patch("app.services.deepl_service.deepl.Translator")
    def test_write_optimize_error_raises_exception(self, mock_translator_cls):
        """write_optimize() should raise exception on API error."""
        mock_translator = MagicMock()
        mock_translator.translate_text.side_effect = Exception("DeepL API Error")

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        with pytest.raises(Exception) as exc_info:
            service.write_optimize("test", target_lang="DE")

        assert "DeepL API Error" in str(exc_info.value)

    @patch("app.services.deepl_service.deepl.Translator")
    def test_get_usage_returns_api_usage(self, mock_translator_cls):
        """get_usage() should return real usage from DeepL API."""
        mock_translator = MagicMock()

        # Mock usage object
        mock_usage = MagicMock()
        mock_usage.character.count = 10000
        mock_usage.character.limit = 500000
        mock_translator.get_usage.return_value = mock_usage

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.get_usage()

        assert result["character_count"] == 10000
        assert result["character_limit"] == 500000

    @patch("app.services.deepl_service.deepl.Translator")
    def test_get_usage_fallback_for_missing_character_detail(self, mock_translator_cls):
        """get_usage() should handle older SDK versions without character detail."""
        mock_translator = MagicMock()

        # Mock usage with flat attributes (older SDK)
        mock_usage = MagicMock()
        del mock_usage.character  # Remove character attribute
        mock_usage.character_count = 25000
        mock_usage.character_limit = 500000
        mock_translator.get_usage.return_value = mock_usage

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.get_usage()

        assert result["character_count"] == 25000

    @patch("app.services.deepl_service.deepl.Translator")
    def test_get_usage_error_returns_fallback(self, mock_translator_cls):
        """get_usage() should return fallback on error."""
        mock_translator = MagicMock()
        mock_translator.get_usage.side_effect = Exception("Network error")

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.get_usage()

        # Should return fallback values
        assert result["character_count"] == 0
        assert result["character_limit"] > 0


class TestDeepLServiceBilledCharacters:
    """Tests for Bug #5 — billed_characters returned from SDK instead of len(text)."""

    def test_translate_mock_mode_includes_billed_characters(self):
        """translate() in mock mode must include billed_characters equal to len(text)."""
        service = DeepLService()
        service._mock_mode = True

        text = "Hello world"
        result = service.translate(text, target_lang="DE")

        assert "billed_characters" in result
        assert result["billed_characters"] == len(text)

    def test_write_optimize_mock_mode_includes_billed_characters(self):
        """write_optimize() in mock mode must include billed_characters equal to len(text)."""
        service = DeepLService()
        service._mock_mode = True

        text = "Some text to optimize"
        result = service.write_optimize(text, target_lang="DE")

        assert "billed_characters" in result
        assert result["billed_characters"] == len(text)

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_returns_sdk_billed_characters(self, mock_translator_cls):
        """translate() must return billed_characters from the SDK result object."""
        mock_translator = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Übersetzter Text"
        mock_result.detected_source_lang = "EN"
        mock_result.billed_characters = 99
        mock_translator.translate_text.return_value = mock_result

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.translate("Hello world", target_lang="DE")

        assert result["billed_characters"] == 99

    @patch("app.services.deepl_service.deepl.Translator")
    def test_translate_falls_back_to_len_when_no_sdk_attribute(
        self, mock_translator_cls
    ):
        """translate() must fall back to len(text) if billed_characters is absent."""
        mock_translator = MagicMock()
        mock_result = MagicMock(spec=["text", "detected_source_lang"])
        mock_result.text = "Übersetzter Text"
        mock_result.detected_source_lang = "EN"
        mock_translator.translate_text.return_value = mock_result

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        text = "Hello world"
        result = service.translate(text, target_lang="DE")

        assert result["billed_characters"] == len(text)

    @patch("app.services.deepl_service.deepl.Translator")
    def test_write_optimize_sums_both_billed_characters(self, mock_translator_cls):
        """write_optimize() must return the sum of billed_characters from both API calls."""
        mock_translator = MagicMock()

        mock_result1 = MagicMock()
        mock_result1.text = "Intermediate text"
        mock_result1.detected_source_lang = "EN"
        mock_result1.billed_characters = 30

        mock_result2 = MagicMock()
        mock_result2.text = "Optimized text"
        mock_result2.billed_characters = 45

        mock_translator.translate_text.side_effect = [mock_result1, mock_result2]

        service = DeepLService()
        service._translator = mock_translator
        service._mock_mode = False

        result = service.write_optimize("Some text", target_lang="DE")

        assert result["billed_characters"] == 75  # 30 + 45


class TestDeepLServiceIntermediateLanguage:
    """Tests for intermediate language mapping in double translation."""

    @pytest.mark.parametrize(
        "target,expected_intermediate",
        [
            ("DE", "EN-GB"),
            ("EN-GB", "DE"),
            ("EN-US", "DE"),
            ("FR", "DE"),
            ("ES", "DE"),
            ("PT-PT", "EN-GB"),
            ("PT-BR", "EN-GB"),
            ("ZH", "EN-GB"),
            ("JA", "EN-GB"),
        ],
    )
    def test_intermediate_language_mapping(self, target, expected_intermediate):
        """Verify intermediate language is correctly mapped for various targets."""
        from app.services.deepl_service import _LANG_INTERMEDIATE

        upper_target = target.upper()
        assert _LANG_INTERMEDIATE.get(upper_target) == expected_intermediate


class TestDeepLServiceCanonicalTarget:
    """Tests for source language canonicalization."""

    @pytest.mark.parametrize(
        "input_lang,expected",
        [
            ("en", "EN-GB"),
            ("EN", "EN-GB"),
            ("pt", "PT-PT"),
            ("PT", "PT-PT"),
            ("zh", "ZH-HANS"),
            ("ZH", "ZH-HANS"),
            ("de", "DE"),  # Should remain unchanged
            ("fr", "FR"),  # Should remain unchanged
        ],
    )
    def test_canonical_target_conversion(self, input_lang, expected):
        """Verify source language codes are canonicalized correctly."""
        from app.services.deepl_service import _canonical_target

        result = _canonical_target(input_lang)
        assert result == expected
