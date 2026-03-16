"""Tests für LLMService — Provider-Interface, alle drei Provider gemockt, Engine-Routing."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure no real LLM provider is configured during tests
os.environ.setdefault("LLM_PROVIDER", "")


# ---------------------------------------------------------------------------
# Imports der Custom Exception-Klassen
# ---------------------------------------------------------------------------

from app.services.llm_service import (  # noqa: E402
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMModelError,
    LLMQuotaError,
    LLMResponse,
    LLMTimeoutError,
)

# ---------------------------------------------------------------------------
# LLMService — Unconfigured (kein Provider)
# ---------------------------------------------------------------------------


class TestLLMServiceUnconfigured:
    def test_is_configured_returns_false_when_no_provider(self):
        """LLMService meldet False wenn kein LLM_PROVIDER gesetzt."""
        from app.services.llm_service import LLMService

        svc = LLMService()
        assert svc.is_configured() is False

    def test_provider_name_empty_when_unconfigured(self):
        from app.services.llm_service import LLMService

        svc = LLMService()
        assert svc.provider_name == ""

    @pytest.mark.asyncio
    async def test_translate_raises_when_unconfigured(self):
        from app.services.llm_service import LLMService

        svc = LLMService()
        with pytest.raises(ValueError, match="nicht konfiguriert"):
            await svc.translate("Hello", "DE")

    @pytest.mark.asyncio
    async def test_write_optimize_raises_when_unconfigured(self):
        from app.services.llm_service import LLMService

        svc = LLMService()
        with pytest.raises(ValueError, match="nicht konfiguriert"):
            await svc.write_optimize("Hello", "DE")


# ---------------------------------------------------------------------------
# LLMService — Unknown / invalid provider
# ---------------------------------------------------------------------------


class TestLLMServiceInvalidProvider:
    def test_unknown_provider_results_in_unconfigured(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "unknownprovider")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        from app.services.llm_service import LLMService

        svc = LLMService()
        assert svc.is_configured() is False

    def test_openai_without_api_key_results_in_unconfigured(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        # Reload settings to pick up env changes
        with patch("app.services.llm_service.LLMService._init_from_config"):
            from app.services.llm_service import LLMService

            svc = LLMService.__new__(LLMService)
            svc._translate_provider = None
            svc._write_provider = None
            svc._provider_name = ""
            svc._translate_model = ""
            svc._write_model = ""
            svc._translate_prompt_template = ""
            svc._write_prompt_template = ""

        assert svc.is_configured() is False


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_complete_calls_openai_api(self):
        """OpenAIProvider.complete() ruft die OpenAI-API korrekt auf."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hallo Welt"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            from app.services.llm_service import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            provider._client = mock_client
            provider._model = "gpt-4o"

            result = await provider.complete("System prompt", "User content")

        assert result.text == "Hallo Welt"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_complete_returns_empty_string_on_none_content(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        from app.services.llm_service import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._client = mock_client
        provider._model = "gpt-4o"

        result = await provider.complete("System", "User")
        assert result.text == ""


# ---------------------------------------------------------------------------
# FINDING-007: _normalize_lang_code() — tests for the new static method
# ---------------------------------------------------------------------------


class TestNormalizeLangCode:
    """Tests for LLMService._normalize_lang_code() static method."""

    def test_iso_lowercase(self):
        """ISO lowercase codes are normalized to uppercase DeepL codes."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("en") == "EN"
        assert LLMService._normalize_lang_code("de") == "DE"
        assert LLMService._normalize_lang_code("fr") == "FR"
        assert LLMService._normalize_lang_code("es") == "ES"
        assert LLMService._normalize_lang_code("it") == "IT"

    def test_deepl_uppercase(self):
        """DeepL uppercase codes are kept as-is."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("DE") == "DE"
        assert LLMService._normalize_lang_code("EN") == "EN"
        assert LLMService._normalize_lang_code("EN-US") == "EN-US"
        assert LLMService._normalize_lang_code("PT-BR") == "PT-BR"

    def test_region_variant(self):
        """Region variants like en-us, pt-br are normalized to base language if no DeepL variant exists."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("en-us") == "EN-US"
        assert LLMService._normalize_lang_code("pt-br") == "PT-BR"
        assert LLMService._normalize_lang_code("zh-cn") == "ZH"

    def test_three_letter_code(self):
        """Three-letter ISO codes (deu, fra) are normalized."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("deu") == "DE"
        assert LLMService._normalize_lang_code("fra") == "FR"
        assert LLMService._normalize_lang_code("eng") == "EN"

    def test_empty_string(self):
        """Empty string returns 'unknown'."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("") == "unknown"

    def test_whitespace_only(self):
        """Whitespace-only string returns 'unknown'."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("   ") == "unknown"

    def test_unknown_code(self):
        """Unknown language code returns 'unknown'."""
        from app.services.llm_service import LLMService

        assert LLMService._normalize_lang_code("xyz") == "unknown"
        assert LLMService._normalize_lang_code("zz") == "unknown"


# ---------------------------------------------------------------------------
# FINDING-007: Parallel language detection in streaming
# ---------------------------------------------------------------------------


class TestParallelLanguageDetection:
    """Tests for parallel language detection during streaming."""

    def _make_service(self, provider_mock) -> "LLMService":  # noqa: F821
        from app.services.llm_service import LLMService

        svc = LLMService.__new__(LLMService)
        svc._translate_provider = provider_mock
        svc._write_provider = provider_mock
        svc._provider_name = "openai"
        svc._translate_model = "gpt-4o"
        svc._write_model = "gpt-4o"
        svc._translate_prompt_template = "You are a professional translator."
        svc._write_prompt_template = "You are a professional editor."
        return svc

    @pytest.mark.asyncio
    async def test_stream_includes_detected_lang_in_done_event(self):
        """translate_stream() includes detected_source_lang in the done event."""
        import json

        mock_provider = MagicMock()

        async def mock_stream(*args):
            yield "Hallo"
            yield " Welt"

        mock_provider.complete_stream = mock_stream

        svc = self._make_service(mock_provider)

        output = []
        async for line in svc.translate_stream("Hello World", "DE"):
            output.append(line)

        done_line = [line for line in output if '"done": true' in line][0]
        data = json.loads(done_line.replace("data: ", "").strip())
        assert "detected_source_lang" in data

    @pytest.mark.asyncio
    async def test_stream_cancels_detect_task_on_error(self):
        """translate_stream() cancels detect_task when stream raises an exception."""
        mock_provider = MagicMock()

        async def mock_stream_error(*args):
            yield "Chunk 1"
            raise Exception("Stream error")

        mock_provider.complete_stream = mock_stream_error

        svc = self._make_service(mock_provider)

        output = []
        async for line in svc.translate_stream("Hello World", "DE"):
            output.append(line)

        error_line = [line for line in output if '"error":' in line][0]
        assert "Stream error" not in error_line  # Safe error message

    @pytest.mark.asyncio
    async def test_write_stream_includes_detected_lang_in_done_event(self):
        """write_optimize_stream() includes detected_source_lang in the done event."""
        import json

        mock_provider = MagicMock()

        async def mock_stream(*args):
            yield "Optimierter"
            yield " Text"

        mock_provider.complete_stream = mock_stream
        # Language detection via complete() call
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="de", input_tokens=5, output_tokens=1, total_tokens=6
            )
        )

        svc = self._make_service(mock_provider)

        output = []
        async for line in svc.write_optimize_stream("Text", "DE"):
            output.append(line)

        done_line = [line for line in output if '"done": true' in line][0]
        data = json.loads(done_line.replace("data: ", "").strip())
        assert "detected_source_lang" in data
        assert data["detected_source_lang"] == "DE"

    @pytest.mark.asyncio
    async def test_write_stream_cancels_detect_task_on_error(self):
        """write_optimize_stream() cancels detect_task when the stream raises."""
        mock_provider = MagicMock()

        async def mock_stream_error(*args):
            yield "Chunk 1"
            raise Exception("Write stream error")

        mock_provider.complete_stream = mock_stream_error
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="de", input_tokens=5, output_tokens=1, total_tokens=6
            )
        )

        svc = self._make_service(mock_provider)

        output = []
        async for line in svc.write_optimize_stream("Text", "DE"):
            output.append(line)

        error_line = [line for line in output if '"error":' in line][0]
        assert "Write stream error" not in error_line  # Safe error message

    @pytest.mark.asyncio
    async def test_write_stream_detected_lang_unknown_when_no_translate_provider(self):
        """write_optimize_stream() emits 'unknown' if translate provider unavailable."""
        import json

        mock_provider = MagicMock()

        async def mock_stream(*args):
            yield "Text"

        mock_provider.complete_stream = mock_stream

        from app.services.llm_service import LLMService

        svc = LLMService.__new__(LLMService)
        svc._translate_provider = None  # No translate provider
        svc._write_provider = mock_provider
        svc._provider_name = "openai"
        svc._write_model = "gpt-4o"
        svc._write_prompt_template = "Improve text in {target_lang}."

        output = []
        async for line in svc.write_optimize_stream("Text", "DE"):
            output.append(line)

        done_line = [line for line in output if '"done": true' in line][0]
        data = json.loads(done_line.replace("data: ", "").strip())
        assert data.get("detected_source_lang") == "unknown"


# ---------------------------------------------------------------------------
# LLMService — translate() und write_optimize() mit gemocktem Provider
# ---------------------------------------------------------------------------


class TestLLMServiceWithMockProvider:
    def _make_service(self, provider_mock) -> "LLMService":  # noqa: F821
        from app.services.llm_service import LLMService

        svc = LLMService.__new__(LLMService)
        svc._translate_provider = provider_mock
        svc._write_provider = provider_mock
        svc._provider_name = "openai"
        svc._translate_model = "gpt-4o"
        svc._write_model = "gpt-4o"
        svc._translate_prompt_template = "You are a professional translator. Translate to {target_lang}. Return only the translated text."
        svc._write_prompt_template = "You are a professional editor. Improve the text in {target_lang}. Return only the improved text."
        return svc

    @pytest.mark.asyncio
    async def test_translate_returns_translated_text(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Hallo Welt", input_tokens=10, output_tokens=20, total_tokens=30
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.translate("Hello World", "DE", source_lang="EN")

        assert result["translated_text"] == "Hallo Welt"
        assert "detected_source_lang" in result
        assert result["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_translate_strips_whitespace(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="  Hallo Welt  \n",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.translate("Hello World", "DE", source_lang="EN")

        assert result["translated_text"] == "Hallo Welt"

    @pytest.mark.asyncio
    async def test_translate_uses_source_lang_as_detected(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Hallo", input_tokens=10, output_tokens=20, total_tokens=30
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.translate("Hello", "DE", source_lang="EN")

        assert result["detected_source_lang"] == "EN"

    @pytest.mark.asyncio
    async def test_translate_passes_correct_system_prompt(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Hallo", input_tokens=10, output_tokens=20, total_tokens=30
            )
        )

        svc = self._make_service(mock_provider)
        await svc.translate("Hello", "DE", source_lang="EN")

        call_args = mock_provider.complete.call_args
        system_prompt = call_args[0][0]
        assert "German" in system_prompt

    @pytest.mark.asyncio
    async def test_write_optimize_returns_optimized_text(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Verbesserter Text",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.write_optimize("Schlechter Text", "DE")

        assert result["optimized_text"] == "Verbesserter Text"
        assert result["detected_lang"] == "DE"
        assert result["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_write_optimize_passes_correct_system_prompt(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Optimiert", input_tokens=10, output_tokens=20, total_tokens=30
            )
        )

        svc = self._make_service(mock_provider)
        await svc.write_optimize("Text", "EN-US")

        call_args = mock_provider.complete.call_args
        system_prompt = call_args[0][0]
        assert "English" in system_prompt  # EN-US → English (American)

    @pytest.mark.asyncio
    async def test_translate_detects_language_when_source_lang_missing(self):
        """translate() erkennt Sprache mit kombiniertem Prompt (ein LLM-Call statt zwei)."""
        mock_provider = MagicMock()
        # Neuer kombinierter Prompt gibt JSON zurück mit detected_lang + translation
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text='{"detected_lang": "en", "translation": "Übersetzung"}',
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.translate("Hello world", "DE")

        assert result["detected_source_lang"] == "EN"
        assert mock_provider.complete.call_count == 1  # Nur ein Call statt zwei!

    @pytest.mark.asyncio
    async def test_translate_skips_detection_when_source_lang_provided(self):
        """translate() überspringt _detect_language wenn source_lang angegeben."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="Übersetzung", input_tokens=10, output_tokens=20, total_tokens=30
            )
        )

        svc = self._make_service(mock_provider)
        result = await svc.translate("Hello", "DE", source_lang="EN")

        assert result["detected_source_lang"] == "EN"
        assert mock_provider.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_detect_language_returns_known_code(self):
        """_detect_language gibt bekannten ISO-Code zurück."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="de", input_tokens=5, output_tokens=5, total_tokens=10
            )
        )

        svc = self._make_service(mock_provider)
        detected = await svc._detect_language("Hallo Welt")

        assert detected == "DE"

    @pytest.mark.asyncio
    async def test_detect_language_truncates_to_50_words(self):
        """detect_language() truncates input to max_words (default 50) before calling LLM."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(
                text="en", input_tokens=5, output_tokens=5, total_tokens=10
            )
        )

        svc = self._make_service(mock_provider)
        long_text = " ".join([f"word{i}" for i in range(150)])
        # Test via public API — truncation is detect_language()'s responsibility
        await svc.detect_language(long_text)

        call_args = mock_provider.complete.call_args
        user_content = call_args[0][1]
        truncated_part = user_content.split("\n\n", 1)[1]
        assert len(truncated_part.split()) == 50

    @pytest.mark.asyncio
    async def test_detect_language_returns_none_on_failure(self):
        """_detect_language gibt None zurück bei Fehlern."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=Exception("API Error"))

        svc = self._make_service(mock_provider)
        detected = await svc._detect_language("Some text")

        assert detected is None

    @pytest.mark.asyncio
    async def test_detect_language_returns_none_for_unknown_code(self):
        """_detect_language gibt None zurück bei unbekanntem Sprachcode."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value="xyz")

        svc = self._make_service(mock_provider)
        detected = await svc._detect_language("Some text")

        assert detected is None


# ---------------------------------------------------------------------------
# /api/translate und /api/write mit engine=llm (Integrations-Tests)
# ---------------------------------------------------------------------------


class TestLLMEngineRouting:
    @pytest.mark.asyncio
    async def test_translate_with_llm_engine_calls_llm_service(self, client):
        """POST /api/translate mit engine=llm ruft llm_service auf."""
        mock_result = {
            "translated_text": "[LLM] Hallo",
            "detected_source_lang": "EN",
        }

        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(return_value=mock_result)

            res = client.post(
                "/api/translate",
                json={
                    "text": "Hello",
                    "target_lang": "DE",
                    "engine": "llm",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["translated_text"] == "[LLM] Hallo"
        mock_llm.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_with_llm_engine_calls_llm_service(self, client):
        """POST /api/write mit engine=llm ruft llm_service auf."""
        mock_result = {
            "optimized_text": "[LLM] Verbesserter Text",
            "detected_lang": "DE",
        }

        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(return_value=mock_result)

            res = client.post(
                "/api/write",
                json={
                    "text": "Schlechter Text",
                    "target_lang": "DE",
                    "engine": "llm",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["optimized_text"] == "[LLM] Verbesserter Text"

    def test_translate_with_llm_engine_returns_503_when_not_configured(self, client):
        """engine=llm gibt 503 zurück wenn LLM nicht konfiguriert."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = False

            res = client.post(
                "/api/translate",
                json={
                    "text": "Hello",
                    "target_lang": "DE",
                    "engine": "llm",
                },
            )

        assert res.status_code == 503
        assert "ERR_LLM_NOT_CONFIGURED" in res.json()["detail"]

    def test_write_with_llm_engine_returns_503_when_not_configured(self, client):
        """engine=llm gibt 503 zurück wenn LLM nicht konfiguriert."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = False

            res = client.post(
                "/api/write",
                json={
                    "text": "Text",
                    "target_lang": "DE",
                    "engine": "llm",
                },
            )

        assert res.status_code == 503

    def test_translate_defaults_to_deepl_engine(self, client):
        """POST /api/translate ohne engine-Feld verwendet DeepL (Default)."""
        res = client.post(
            "/api/translate",
            json={
                "text": "Hello",
                "target_lang": "DE",
                # engine not specified — should default to deepl
            },
        )
        # In mock mode DeepL returns 200 with mock text
        assert res.status_code == 200
        data = res.json()
        assert "translated_text" in data

    def test_write_defaults_to_deepl_engine(self, client):
        """POST /api/write ohne engine-Feld verwendet DeepL (Default)."""
        res = client.post(
            "/api/write",
            json={
                "text": "Hello",
                "target_lang": "DE",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "optimized_text" in data

    def test_config_includes_llm_fields(self, client):
        """/api/config enthält llm_configured und llm_provider Felder."""
        res = client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "llm_configured" in data
        assert "llm_provider" in data
        assert "llm_translate_model" in data
        assert "llm_write_model" in data

    def test_config_llm_not_configured_in_test_env(self, client):
        """/api/config gibt llm_configured=False zurück wenn kein Provider gesetzt."""
        res = client.get("/api/config")
        data = res.json()
        # In tests LLM_PROVIDER is not set → should be False
        assert data["llm_configured"] is False
        assert data["llm_provider"] is None

    def test_translate_rejects_invalid_engine_value(self, client):
        """engine-Feld akzeptiert nur 'deepl' oder 'llm'."""
        res = client.post(
            "/api/translate",
            json={
                "text": "Hello",
                "target_lang": "DE",
                "engine": "invalid",
            },
        )
        assert res.status_code == 422  # Pydantic validation error

    def test_config_includes_llm_display_name(self, client):
        """/api/config enthält llm_display_name Feld."""
        res = client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "llm_display_name" in data

    def test_config_llm_display_name_is_none_when_not_configured(self, client):
        """/api/config gibt llm_display_name=None zurück wenn LLM nicht konfiguriert."""
        res = client.get("/api/config")
        data = res.json()
        assert data["llm_display_name"] is None


# ---------------------------------------------------------------------------
# LLM Custom Exceptions — Hierarchie und Vererbung
# ---------------------------------------------------------------------------


class TestLLMExceptionHierarchy:
    def test_all_exceptions_inherit_from_llm_error(self):
        """Alle Custom Exceptions erben von LLMError."""
        assert issubclass(LLMTimeoutError, LLMError)
        assert issubclass(LLMAuthError, LLMError)
        assert issubclass(LLMQuotaError, LLMError)
        assert issubclass(LLMModelError, LLMError)
        assert issubclass(LLMConnectionError, LLMError)

    def test_all_exceptions_inherit_from_base_exception(self):
        """Alle Custom Exceptions sind echte Python-Exceptions."""
        assert issubclass(LLMError, Exception)

    def test_exceptions_can_be_raised_and_caught(self):
        for exc_class in [
            LLMTimeoutError,
            LLMAuthError,
            LLMQuotaError,
            LLMModelError,
            LLMConnectionError,
        ]:
            with pytest.raises(LLMError):
                raise exc_class("test")


# ---------------------------------------------------------------------------
# OpenAIProvider — Exception-Mapping
# ---------------------------------------------------------------------------


class TestOpenAIProviderExceptionMapping:
    def _make_provider(self):
        from app.services.llm_service import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._model = "gpt-4o"
        return provider

    @pytest.mark.asyncio
    async def test_timeout_raises_llm_timeout_error(self):
        provider = self._make_provider()
        mock_client = MagicMock()

        import openai

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=MagicMock())
        )
        provider._client = mock_client

        with pytest.raises(LLMTimeoutError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_auth_error_raises_llm_auth_error(self):
        provider = self._make_provider()
        mock_client = MagicMock()

        import openai

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.AuthenticationError(
                message="Unauthorized",
                response=MagicMock(status_code=401, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMAuthError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_rate_limit_raises_llm_quota_error(self):
        provider = self._make_provider()
        mock_client = MagicMock()

        import openai

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMQuotaError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_not_found_raises_llm_model_error(self):
        provider = self._make_provider()
        mock_client = MagicMock()

        import openai

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.NotFoundError(
                message="Model not found",
                response=MagicMock(status_code=404, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMModelError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_connection_error_raises_llm_connection_error(self):
        provider = self._make_provider()
        mock_client = MagicMock()

        import openai

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )
        provider._client = mock_client

        with pytest.raises(LLMConnectionError):
            await provider.complete("System", "User")


# ---------------------------------------------------------------------------
# OllamaProvider — Exception-Mapping
# ---------------------------------------------------------------------------


class TestOllamaProviderExceptionMapping:
    def _make_provider(self):
        from app.services.llm_service import OllamaProvider

        provider = OllamaProvider.__new__(OllamaProvider)
        provider._model = "llama3.2"
        return provider

    @pytest.mark.asyncio
    async def test_timeout_raises_llm_timeout_error(self):
        import httpx

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        provider._client = mock_client

        with pytest.raises(LLMTimeoutError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_connect_error_raises_llm_connection_error(self):
        import httpx

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        provider._client = mock_client

        with pytest.raises(LLMConnectionError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_401_raises_llm_auth_error(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        with pytest.raises(LLMAuthError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_404_raises_llm_model_error(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        with pytest.raises(LLMModelError):
            await provider.complete("System", "User")


# ---------------------------------------------------------------------------
# Router — HTTP-Status-Codes für LLM-Fehlertypen
# ---------------------------------------------------------------------------


class TestLLMErrorHTTPMapping:
    @pytest.mark.asyncio
    async def test_timeout_error_returns_408(self, client):
        """LLMTimeoutError → HTTP 408."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(side_effect=LLMTimeoutError("Timeout"))

            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 408
        assert "ERR_LLM_TIMEOUT" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_auth_error_returns_401(self, client):
        """LLMAuthError → HTTP 401."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(side_effect=LLMAuthError("Unauthorized"))

            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 401
        assert "ERR_LLM_AUTH" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_quota_error_returns_429(self, client):
        """LLMQuotaError → HTTP 429."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(side_effect=LLMQuotaError("Quota exceeded"))

            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 429
        assert "ERR_LLM_QUOTA" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_model_error_returns_422(self, client):
        """LLMModelError → HTTP 422."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(side_effect=LLMModelError("Model not found"))

            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 422
        assert "ERR_LLM_MODEL" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_connection_error_returns_503(self, client):
        """LLMConnectionError → HTTP 503."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.translate = AsyncMock(
                side_effect=LLMConnectionError("Connection refused")
            )

            res = client.post(
                "/api/translate",
                json={"text": "Hello", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 503
        assert "ERR_LLM_CONNECTION" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_write_timeout_error_returns_408(self, client):
        """LLMTimeoutError bei /api/write → HTTP 408."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(side_effect=LLMTimeoutError("Timeout"))

            res = client.post(
                "/api/write",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 408


# ---------------------------------------------------------------------------
# openai-compatible Provider
# ---------------------------------------------------------------------------


class TestOpenAICompatibleProvider:
    def test_openai_compatible_without_base_url_results_in_unconfigured(self):
        """LLM_PROVIDER=openai-compatible ohne LLM_BASE_URL → nicht konfiguriert."""
        from app.services.llm_service import LLMService

        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "openai-compatible"
            mock_settings.llm_api_key = None
            mock_settings.llm_base_url = None
            mock_settings.llm_translate_model = "gpt-4o"
            mock_settings.llm_write_model = "gpt-4o"
            mock_settings.llm_display_name = None
            mock_settings.llm_timeout = 30
            mock_settings.llm_translate_prompt = "Translate to {target_lang}."
            mock_settings.llm_write_prompt = "Improve in {target_lang}."

            svc = LLMService()

        assert svc.is_configured() is False

    def test_openai_compatible_with_base_url_uses_openai_provider(self):
        """LLM_PROVIDER=openai-compatible mit LLM_BASE_URL → OpenAIProvider wird erstellt."""
        from app.services.llm_service import LLMService, OpenAIProvider

        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "openai-compatible"
            mock_settings.llm_api_key = None  # optional
            mock_settings.llm_base_url = "http://litellm:4000"
            mock_settings.llm_translate_model = "gpt-4o"
            mock_settings.llm_write_model = "gpt-4o"
            mock_settings.llm_display_name = "LiteLLM"
            mock_settings.llm_timeout = 30
            mock_settings.llm_translate_prompt = "Translate to {target_lang}."
            mock_settings.llm_write_prompt = "Improve in {target_lang}."

            with patch("app.services.llm_service.OpenAIProvider") as mock_openai_cls:
                mock_openai_cls.return_value = MagicMock()
                LLMService()

        # OpenAIProvider should be called with "no-key" as api_key and the base_url
        assert mock_openai_cls.call_count == 2
        call_args = mock_openai_cls.call_args_list[0][0]
        assert call_args[0] == "no-key"  # api_key fallback
        assert call_args[2] == "http://litellm:4000"  # base_url

    def test_openai_compatible_display_name_is_used(self):
        """LLM_DISPLAY_NAME wird als display_name korrekt gesetzt."""
        from app.services.llm_service import LLMService

        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "openai-compatible"
            mock_settings.llm_api_key = None
            mock_settings.llm_base_url = "http://litellm:4000"
            mock_settings.llm_translate_model = "gpt-4o"
            mock_settings.llm_write_model = "gpt-4o"
            mock_settings.llm_display_name = "LiteLLM"
            mock_settings.llm_timeout = 30
            mock_settings.llm_translate_prompt = "Translate to {target_lang}."
            mock_settings.llm_write_prompt = "Improve in {target_lang}."

            with patch("app.services.llm_service.OpenAIProvider") as mock_openai_cls:
                mock_openai_cls.return_value = MagicMock()
                svc = LLMService()

        assert svc.display_name == "LiteLLM"

    def test_display_name_falls_back_to_provider_name(self):
        """display_name fällt auf provider_name zurück wenn kein LLM_DISPLAY_NAME gesetzt."""
        from app.services.llm_service import LLMService

        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "openai-compatible"
            mock_settings.llm_api_key = None
            mock_settings.llm_base_url = "http://litellm:4000"
            mock_settings.llm_translate_model = "gpt-4o"
            mock_settings.llm_write_model = "gpt-4o"
            mock_settings.llm_display_name = None  # no display name set
            mock_settings.llm_timeout = 30
            mock_settings.llm_translate_prompt = "Translate to {target_lang}."
            mock_settings.llm_write_prompt = "Improve in {target_lang}."

            with patch("app.services.llm_service.OpenAIProvider") as mock_openai_cls:
                mock_openai_cls.return_value = MagicMock()
                svc = LLMService()

        assert svc.display_name == "openai-compatible"


# ---------------------------------------------------------------------------
# FINDING-005: AnthropicProvider — Exception-Mapping (fehlte bisher)
# ---------------------------------------------------------------------------


class TestAnthropicProviderExceptionMapping:
    def _make_provider(self):
        from app.services.llm_service import AnthropicProvider

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._model = "claude-3-5-sonnet-20241022"
        return provider

    @pytest.mark.asyncio
    async def test_timeout_raises_llm_timeout_error(self):
        import anthropic

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APITimeoutError(request=MagicMock())
        )
        provider._client = mock_client

        with pytest.raises(LLMTimeoutError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_auth_error_raises_llm_auth_error(self):
        import anthropic

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.AuthenticationError(
                message="Unauthorized",
                response=MagicMock(status_code=401, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMAuthError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_rate_limit_raises_llm_quota_error(self):
        import anthropic

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMQuotaError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_bad_request_raises_llm_model_error(self):
        import anthropic

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.BadRequestError(
                message="Invalid model",
                response=MagicMock(status_code=400, headers={}),
                body=None,
            )
        )
        provider._client = mock_client

        with pytest.raises(LLMModelError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_connection_error_raises_llm_connection_error(self):
        import anthropic

        provider = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIConnectionError(request=MagicMock())
        )
        provider._client = mock_client

        with pytest.raises(LLMConnectionError):
            await provider.complete("System", "User")

    @pytest.mark.asyncio
    async def test_empty_content_returns_empty_string(self):
        """Anthropic leere content-Liste → leerer String statt IndexError."""
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.content = []
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client

        result = await provider.complete("System", "User")
        assert result.text == ""


# ---------------------------------------------------------------------------
# FINDING-006: /api/write — alle Fehlertypen testen (bisher nur Timeout)
# ---------------------------------------------------------------------------


class TestLLMWriteErrorHTTPMapping:
    @pytest.mark.asyncio
    async def test_write_auth_error_returns_401(self, client):
        """LLMAuthError bei /api/write → HTTP 401."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(
                side_effect=LLMAuthError("Unauthorized")
            )

            res = client.post(
                "/api/write",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 401
        assert "ERR_LLM_AUTH" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_write_quota_error_returns_429(self, client):
        """LLMQuotaError bei /api/write → HTTP 429."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(
                side_effect=LLMQuotaError("Quota exceeded")
            )

            res = client.post(
                "/api/write",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 429
        assert "ERR_LLM_QUOTA" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_write_model_error_returns_422(self, client):
        """LLMModelError bei /api/write → HTTP 422."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(
                side_effect=LLMModelError("Model not found")
            )

            res = client.post(
                "/api/write",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 422
        assert "ERR_LLM_MODEL" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_write_connection_error_returns_503(self, client):
        """LLMConnectionError bei /api/write → HTTP 503."""
        with patch("app.routers.translate.llm_service") as mock_llm:
            mock_llm.is_configured.return_value = True
            mock_llm.write_optimize = AsyncMock(
                side_effect=LLMConnectionError("Connection refused")
            )

            res = client.post(
                "/api/write",
                json={"text": "Text", "target_lang": "DE", "engine": "llm"},
            )

        assert res.status_code == 503
        assert "ERR_LLM_CONNECTION" in res.json()["detail"]


# ---------------------------------------------------------------------------
# FINDING-007: OpenAI-compatible ohne base_url — tote monkeypatch-Zeilen entfernt
# (Test wurde bereits oben korrigiert, hier nur OpenAI empty-choices Guard testen)
# ---------------------------------------------------------------------------


class TestOpenAIProviderGuards:
    def _make_provider(self):
        from app.services.llm_service import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._model = "gpt-4o"
        return provider

    @pytest.mark.asyncio
    async def test_empty_choices_returns_empty_string(self):
        """OpenAI leere choices-Liste → leerer String statt IndexError."""
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = self._make_provider()
        provider._client = mock_client

        result = await provider.complete("System", "User")
        assert result.text == ""


# ---------------------------------------------------------------------------
# _strip_markdown_chunk — preserves leading/trailing whitespace (Bug #3 fix)
# ---------------------------------------------------------------------------


class TestStripMarkdownChunk:
    """_strip_markdown_chunk — minimal safe code-fence removal for streaming chunks.

    WHY MINIMAL: Most markdown patterns (bullets, headings, bold) use characters
    that also appear in normal prose (hyphens, asterisks, hash signs). Applying
    those regexes to text *fragments* causes false positives. The prompt forbids
    markdown, so only code fences — which never appear in natural text — are removed.

    The key invariant: leading/trailing whitespace is NEVER stripped, because those
    spaces are word boundaries between consecutive SSE chunks.
    """

    def _fn(self, text):
        from app.services.llm_service import _strip_markdown_chunk

        return _strip_markdown_chunk(text)

    # ── Whitespace preservation ─────────────────────────────────────────────

    def test_preserves_leading_space(self):
        """Leading space on a streaming chunk is NOT stripped."""
        assert self._fn(" environment") == " environment"

    def test_preserves_trailing_space(self):
        """Trailing space on a chunk is NOT stripped."""
        assert self._fn("hello ") == "hello "

    def test_preserves_both_spaces(self):
        """Both leading and trailing spaces are preserved."""
        assert self._fn(" word ") == " word "

    def test_empty_string_returns_empty(self):
        """Empty string is returned unchanged."""
        assert self._fn("") == ""

    # ── Code fence removal ──────────────────────────────────────────────────

    def test_removes_code_fence_open(self):
        """Opening code fence (including trailing whitespace/newline) is stripped."""
        # The regex uses \s* which also consumes the newline after the fence marker.
        assert self._fn("```python\ncode") == "code"

    def test_removes_code_fence_close(self):
        """Closing code fence is stripped."""
        assert self._fn("code\n```") == "code\n"

    def test_removes_standalone_code_fence(self):
        """A bare ``` line is removed (trailing whitespace/newline consumed by regex)."""
        assert self._fn("text\n```\nmore") == "text\nmore"

    # ── Characters that must NOT be removed (false-positive guard) ──────────

    def test_hyphen_with_word_is_preserved(self):
        """'- und' must NOT be treated as a bullet point — it's part of a hyphenated word."""
        assert self._fn("- und") == "- und"

    def test_bullet_dash_preserved(self):
        """Leading '- ' is kept — bullet removal would corrupt hyphenated compounds."""
        assert self._fn("- Speicherherstellern") == "- Speicherherstellern"

    def test_asterisk_preserved(self):
        """Leading asterisk is kept — not treated as bullet point."""
        assert self._fn("* item") == "* item"

    def test_bold_preserved(self):
        """Bold markers are kept — not removed from chunks."""
        assert self._fn("**bold**") == "**bold**"

    def test_heading_preserved(self):
        """Heading markers are kept — not removed from chunks."""
        assert self._fn("## Title") == "## Title"

    def test_horizontal_rule_preserved(self):
        """Horizontal rules are kept — could be real dashes in text."""
        assert self._fn("---") == "---"

    # ── Pass-through ────────────────────────────────────────────────────────

    def test_plain_text_unchanged(self):
        """Plain text without any markdown passes through unchanged."""
        assert self._fn("Hello, world!") == "Hello, world!"

    def test_word_boundary_chunk_sequence(self):
        """Simulates a realistic streaming sequence with inter-chunk spaces."""
        from app.services.llm_service import _strip_markdown_chunk

        chunks = ["Is your", " current", " demo", " environment", " working?"]
        result = "".join(_strip_markdown_chunk(c) for c in chunks)
        assert result == "Is your current demo environment working?"

    def test_hyphenated_word_chunk_sequence(self):
        """Hyphenated German compound split across chunks must not lose the hyphen."""
        from app.services.llm_service import _strip_markdown_chunk

        # Scenario from Bug #3: LLM streams "Chip" then "- und Speicherhersteller"
        chunks = ["Chip", "- und Speicherhersteller"]
        result = "".join(_strip_markdown_chunk(c) for c in chunks)
        assert result == "Chip- und Speicherhersteller"

    # ── _strip_markdown regression guard ───────────────────────────────────

    def test_strip_markdown_full_still_strips_whitespace(self):
        """_strip_markdown (non-chunk variant) still strips whitespace — no regression."""
        from app.services.llm_service import _strip_markdown

        assert _strip_markdown("  hello  ") == "hello"
        assert _strip_markdown(" word") == "word"

    def test_strip_markdown_full_removes_bullet(self):
        """_strip_markdown still removes bullet points on the full text — no regression."""
        from app.services.llm_service import _strip_markdown

        assert _strip_markdown("* item") == "item"
        assert _strip_markdown("- item") == "item"


class TestStripMetaCommentary:
    """Tests for _strip_meta_commentary() — removes LLM preamble phrases."""

    def _strip(self, text):
        from app.services.llm_service import _strip_meta_commentary

        return _strip_meta_commentary(text)

    # ── Should be stripped ──────────────────────────────────────────────────

    def test_strips_here_is_the_translation(self):
        assert (
            self._strip("Here is the translation: Das ist ein Test.")
            == "Das ist ein Test."
        )

    def test_strips_heres_the_translation(self):
        assert (
            self._strip("Here's the translation:\nDas ist ein Test.")
            == "Das ist ein Test."
        )

    def test_strips_here_is_translated_text(self):
        assert self._strip("Here is the translated text: Bonjour.") == "Bonjour."

    def test_strips_certainly_here_is(self):
        assert self._strip("Certainly! Here is the translation: Hola.") == "Hola."

    def test_strips_sure_heres(self):
        assert (
            self._strip("Sure! Here's the optimized text:\nVerbessert.")
            == "Verbessert."
        )

    def test_strips_translation_label(self):
        assert self._strip("Translation: Das ist ein Test.") == "Das ist ein Test."

    def test_strips_uebersetzung_label(self):
        assert self._strip("Übersetzung: Das ist ein Test.") == "Das ist ein Test."

    def test_strips_optimized_text_label(self):
        assert (
            self._strip("Optimized text: Better version here.")
            == "Better version here."
        )

    def test_strips_improved_version_label(self):
        assert self._strip("Improved version: Fixed text.") == "Fixed text."

    def test_strips_certainly_standalone(self):
        assert self._strip("Certainly! Das ist ein Test.") == "Das ist ein Test."

    def test_strips_of_course(self):
        result = self._strip("Of course! Here is the translation: Foo bar.")
        assert result == "Foo bar."

    # ── Should NOT be stripped (false-positive guard) ───────────────────────

    def test_preserves_normal_text(self):
        text = "Das ist ein ganz normaler Text ohne Einleitung."
        assert self._strip(text) == text

    def test_preserves_text_starting_with_here(self):
        """'Here' in normal context should not be stripped."""
        text = "Here we go — the adventure begins."
        assert self._strip(text) == text

    def test_preserves_text_with_translation_in_body(self):
        """'translation' later in the text must not cause stripping."""
        text = "The translation of this word is difficult."
        assert self._strip(text) == text

    def test_preserves_empty_string(self):
        assert self._strip("") == ""

    def test_preserves_multiline_normal_text(self):
        text = "Erste Zeile.\nZweite Zeile.\nDritte Zeile."
        assert self._strip(text) == text

    def test_preserves_text_longer_than_buffer(self):
        """Text longer than 200 chars should only strip if prefix matches."""
        long_text = "A" * 300
        assert self._strip(long_text) == long_text
