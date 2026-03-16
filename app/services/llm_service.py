"""LLM service — abstraktes Provider-Interface mit OpenAI, Anthropic, Ollama und OpenAI-kompatiblen Proxys."""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response-Typ mit Token-Nutzung
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Response von LLM-Providern inklusive Token-Nutzung."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


def _strip_markdown(text: str) -> str:
    """Entfernt alle Markdown-Formatierungen aus dem Text.

    LLMs geben manchmal ungewollt Markdown aus (Fences, Bulletpoints, etc.).
    Diese Funktion bereinigt das Ergebnis für die Plain-Text-Ausgabe.

    Entfernt:
    - Markdown code fences (``` und ```)
    - Inline code marks (` und `)
    - Bullet points (*, -, + am Zeilenanfang)
    - Numbered lists (1., 2., etc.)
    - Bold/Italic/Strikethrough markers (**, *, ~~)
    - Headings (# bis ####)
    - Horizontal rules (---, ***, ___)

    Fixes spacing issues:
    - Adds space after punctuation followed by a letter
    - Fixes colon-digit pattern (Buildings:18 → Buildings: 18)
    - Fixes possessive+capital pattern (Peter'sHome → Peter's Home)
    - Fixes CamelCase/concatenated words

    Returns:
        Bereinigter Plain-Text ohne Formatierung.
    """
    if not text:
        return text

    # Step 1: Entferne Markdown code fences (```...```)
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    # Step 2: Entferne inline code markers (`...`)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Step 3: Entferne Überschriften (# bis ######)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Step 4: Entferne horizontale Linien (---, ***, ___)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Step 5: Entferne Bulletpoints (*, -, +) am Zeilenanfang
    text = re.sub(r"^[\*\-\+]\s+", "", text, flags=re.MULTILINE)

    # Step 6: Entferne numbered lists (1., 2., etc.)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)

    # Step 7: Entferne Bold/Italic/Strikethrough (*, **, ~~)
    # Must handle ** before * to avoid nested issues
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)

    # Step 8: Entferne Links [text](url) - behalte nur den Text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Step 9: Normalize multiple spaces to single space (but preserve paragraph breaks)
    # Split by double newline (paragraph break), normalize spaces in each paragraph, join back
    paragraphs = text.split("\n\n")
    paragraphs = [re.sub(r" {2,}", " ", p).strip() for p in paragraphs]
    text = "\n\n".join(paragraphs)

    # Step 10: Remove remaining leading/trailing whitespace.
    # NOTE: Do NOT call _strip_markdown() on individual streaming chunks —
    # .strip() removes leading/trailing spaces that are word boundaries between
    # chunks, causing words to concatenate ("demo environment" → "demoenvironment").
    # For streaming, use _strip_markdown_chunk() which skips this step.
    text = text.strip()

    return text


def _strip_markdown_chunk(chunk: str) -> str:
    """Minimal safe markdown removal for individual streaming chunks.

    WHY THIS IS INTENTIONALLY MINIMAL:
    Most markdown patterns (bullet points, headings, bold, horizontal rules)
    use characters that also appear in normal prose — hyphens in compound words,
    asterisks in footnotes, hash symbols in IDs, etc. Applying those regexes to
    text *fragments* causes false positives that delete real content.

    The prompt already explicitly forbids all markdown. This function is only a
    last-resort safety net for the very few patterns that NEVER appear in normal
    text: backtick code fences. Everything else is left to _strip_markdown() which
    operates on the fully accumulated text after streaming completes.

    Does NOT call .strip() — leading/trailing spaces are word boundaries between
    consecutive chunks and must be preserved to avoid word concatenation.
    """
    if not chunk:
        return chunk

    # Remove opening code fence (```python, ```json, etc.)
    # These are unambiguous — backtick fences never appear in natural language.
    chunk = re.sub(r"^```[a-zA-Z]*\s*", "", chunk, flags=re.MULTILINE)
    # Remove closing code fence
    chunk = re.sub(r"```\s*$", "", chunk, flags=re.MULTILINE)
    # Remove standalone triple-backtick lines (e.g. bare ``` on its own line)
    chunk = re.sub(r"^```\s*$", "", chunk, flags=re.MULTILINE)

    # NOTE: No .strip() — leading/trailing spaces are word boundaries!
    return chunk


# ---------------------------------------------------------------------------
# Meta-commentary stripping
# ---------------------------------------------------------------------------

# Matches LLM preamble phrases that appear ONLY at the very start of the response.
# We check only the first 200 characters to avoid false positives in body text.
# Pattern: optional "certainly/sure/of course", then an optional "here is/here's"
# phrase followed by a colon or newline that introduces the actual content.
_META_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:(?:certainly|sure|of\s+course|absolutely)[!,.]?\s*)?"  # optional opener
    r"(?:here\s+(?:is|are)|here's)\s+(?:the\s+)?(?:translation|translated|optimized|improved|result|text|version)[^:\n]*[:\n]\s*"
    r"|(?:certainly|sure|of\s+course|absolutely)[!,.]\s*"  # standalone opener with punctuation
    r"|(?:translation|übersetzung|traduction|traduzione|traducción)\s*:\s*"  # bare label
    r"|(?:optimized|improved|edited|revised)\s+(?:text|version)\s*:\s*"  # write label
    r")",
    re.IGNORECASE,
)


def _strip_meta_commentary(text: str) -> str:
    """Remove LLM preamble phrases from the start of a response.

    Only inspects the first 200 characters. If a known intro phrase is found
    at the very beginning, it is stripped. The rest of the text is returned
    unchanged to avoid false positives in body content.

    Examples removed:
      "Here is the translation: Das ist ein Test."  → "Das ist ein Test."
      "Certainly! Here's the translated text:\nFoo" → "Foo"
      "Translation: Das ist ein Test."              → "Das ist ein Test."
      "Sure, here is the result:\nFoo"              → "Foo"
    """
    if not text:
        return text
    # Only check the first 200 characters for a prefix match
    head = text[:200]
    m = _META_PREFIX_RE.match(head)
    if m:
        text = text[m.end() :]
    return text


# ---------------------------------------------------------------------------
# Custom Exception-Hierarchie — provider-agnostisch
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Basisklasse für alle LLM-Fehler. Wird im Router gezielt gefangen."""


class LLMTimeoutError(LLMError):
    """LLM hat nicht innerhalb des konfigurierten Timeouts geantwortet."""


class LLMAuthError(LLMError):
    """API-Key fehlt, ist ungültig oder abgelaufen."""


class LLMQuotaError(LLMError):
    """Credits erschöpft oder Rate Limit des Providers erreicht."""


class LLMModelError(LLMError):
    """Modell nicht gefunden, nicht verfügbar oder Anfrage für dieses Modell ungültig."""


class LLMConnectionError(LLMError):
    """Provider nicht erreichbar (Netzwerkfehler, falsche URL, DNS-Fehler)."""


# ---------------------------------------------------------------------------
# Safe error messages for streaming — never expose internal provider details
# ---------------------------------------------------------------------------

_SAFE_STREAM_ERRORS: dict[type, str] = {
    LLMTimeoutError: "LLM antwortet nicht (Timeout).",
    LLMAuthError: "LLM API-Schlüssel ungültig.",
    LLMQuotaError: "LLM Rate Limit oder Credits erschöpft.",
    LLMModelError: "LLM-Modell nicht verfügbar.",
    LLMConnectionError: "LLM nicht erreichbar.",
}


def _safe_stream_error_msg(exc: Exception) -> str:
    """Map an LLM exception to a safe, user-facing message.

    Never exposes internal provider details (API URLs, partial keys, etc.).
    Falls back to a generic message for unknown exception types.
    """
    for exc_type, msg in _SAFE_STREAM_ERRORS.items():
        if isinstance(exc, exc_type):
            return msg
    return "LLM-Fehler. Bitte versuche es erneut."


# Mapping von DeepL-Sprachcodes auf lesbare Namen für System-Prompts
_LANG_NAMES: dict[str, str] = {
    "AR": "Arabic",
    "BG": "Bulgarian",
    "CS": "Czech",
    "DA": "Danish",
    "DE": "German",
    "EL": "Greek",
    "EN": "English",
    "EN-GB": "English (British)",
    "EN-US": "English (American)",
    "ES": "Spanish",
    "ET": "Estonian",
    "FI": "Finnish",
    "FR": "French",
    "HU": "Hungarian",
    "ID": "Indonesian",
    "IT": "Italian",
    "JA": "Japanese",
    "KO": "Korean",
    "LT": "Lithuanian",
    "LV": "Latvian",
    "NB": "Norwegian",
    "NL": "Dutch",
    "PL": "Polish",
    "PT": "Portuguese",
    "PT-BR": "Portuguese (Brazilian)",
    "PT-PT": "Portuguese (European)",
    "RO": "Romanian",
    "RU": "Russian",
    "SK": "Slovak",
    "SL": "Slovenian",
    "SV": "Swedish",
    "TR": "Turkish",
    "UK": "Ukrainian",
    "ZH": "Chinese",
    "ZH-HANS": "Chinese (Simplified)",
}

_ISO_TO_DEEPL: dict[str, str] = {
    "en": "EN",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "pt": "PT",
    "ru": "RU",
    "zh": "ZH",
    "ja": "JA",
    "ko": "KO",
    "ar": "AR",
    "bg": "BG",
    "cs": "CS",
    "da": "DA",
    "el": "EL",
    "et": "ET",
    "fi": "FI",
    "hu": "HU",
    "id": "ID",
    "lt": "LT",
    "lv": "LV",
    "nb": "NB",
    "nl": "NL",
    "pl": "PL",
    "ro": "RO",
    "sk": "SK",
    "sl": "SL",
    "sv": "SV",
    "tr": "TR",
    "uk": "UK",
}


def _lang_name(code: str) -> str:
    """Gibt den lesbaren Sprachnamen für einen Code zurück (Fallback: Code selbst)."""
    return _LANG_NAMES.get(code.upper(), code)


# ---------------------------------------------------------------------------
# Abstraktes Provider-Interface
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Basis-Interface für alle LLM-Provider."""

    @abstractmethod
    async def complete(self, system_prompt: str, user_content: str) -> LLMResponse:
        """Sendet eine Anfrage und gibt die Antwort inklusive Token-Nutzung zurück."""

    async def complete_stream(
        self, system_prompt: str, user_content: str
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """Streaming-Variante: Liefert Token-für-Token als AsyncGenerator.

        Yields text chunks (str) followed by a final LLMResponse sentinel
        containing the token usage. Callers that only want text can ignore
        non-str values; callers that need usage data check for LLMResponse.

        Standard-Implementierung fällt auf complete() zurück (kein echtes Streaming).
        Provider können diese Methode überschreiben für native Streaming-Unterstützung.
        """
        response = await self.complete(system_prompt, user_content)
        yield response.text
        yield response  # sentinel with token counts


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415

            kwargs: dict = {"api_key": api_key, "timeout": timeout}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = AsyncOpenAI(**kwargs)
        except ImportError as exc:
            raise RuntimeError(
                "openai package nicht installiert. 'pip install openai' ausführen."
            ) from exc
        self._model = model

    async def complete(self, system_prompt: str, user_content: str) -> LLMResponse:
        import openai  # noqa: PLC0415 — already cached in sys.modules; needed for exception types

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
            )
            if not response.choices:
                return LLMResponse(text="")
            text = response.choices[0].message.content or ""
            usage = response.usage
            return LLMResponse(
                text=text,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError("OpenAI Timeout") from exc
        except openai.AuthenticationError as exc:
            raise LLMAuthError("OpenAI Authentifizierung fehlgeschlagen") from exc
        except openai.RateLimitError as exc:
            raise LLMQuotaError("OpenAI Rate Limit oder Credits erschöpft") from exc
        except openai.NotFoundError as exc:
            raise LLMModelError(f"OpenAI Modell nicht gefunden: {self._model}") from exc
        except openai.APIConnectionError as exc:
            raise LLMConnectionError("OpenAI nicht erreichbar") from exc
        except openai.APIError as exc:
            raise LLMError(
                f"OpenAI API-Fehler: HTTP {getattr(exc, 'status_code', 'unknown')}"
            ) from exc

    async def complete_stream(
        self, system_prompt: str, user_content: str
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """Streaming via OpenAI stream=True. Yields text chunks, then a final LLMResponse sentinel.

        Uses stream_options={"include_usage": True} so the last chunk contains
        token counts — these are collected and yielded as an LLMResponse after all text.
        """
        import openai  # noqa: PLC0415

        input_tokens = 0
        output_tokens = 0
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                # Usage is reported in the final chunk (choices is empty)
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens or 0
                    output_tokens = chunk.usage.completion_tokens or 0
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError("OpenAI Timeout") from exc
        except openai.AuthenticationError as exc:
            raise LLMAuthError("OpenAI Authentifizierung fehlgeschlagen") from exc
        except openai.RateLimitError as exc:
            raise LLMQuotaError("OpenAI Rate Limit oder Credits erschöpft") from exc
        except openai.NotFoundError as exc:
            raise LLMModelError(f"OpenAI Modell nicht gefunden: {self._model}") from exc
        except openai.APIConnectionError as exc:
            raise LLMConnectionError("OpenAI nicht erreichbar") from exc
        except openai.APIError as exc:
            raise LLMError(
                f"OpenAI API-Fehler: HTTP {getattr(exc, 'status_code', 'unknown')}"
            ) from exc
        # Yield usage sentinel after all text chunks
        yield LLMResponse(
            text="",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )


# ---------------------------------------------------------------------------
# Anthropic Provider
# ---------------------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout: int = 30) -> None:
        try:
            import anthropic  # noqa: PLC0415

            self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package nicht installiert. 'pip install anthropic' ausführen."
            ) from exc
        self._model = model

    async def complete(self, system_prompt: str, user_content: str) -> LLMResponse:
        import anthropic  # noqa: PLC0415 — already cached in sys.modules; needed for exception types

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            if not response.content:
                return LLMResponse(text="")
            block = response.content[0]
            text = block.text if hasattr(block, "text") else ""
            usage = response.usage
            return LLMResponse(
                text=text,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                total_tokens=usage.input_tokens + usage.output_tokens if usage else 0,
            )
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError("Anthropic Timeout") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError("Anthropic Authentifizierung fehlgeschlagen") from exc
        except anthropic.RateLimitError as exc:
            raise LLMQuotaError("Anthropic Rate Limit oder Credits erschöpft") from exc
        except anthropic.BadRequestError as exc:
            raise LLMModelError(f"Anthropic Modell-Fehler: {self._model}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMConnectionError("Anthropic nicht erreichbar") from exc
        except anthropic.APIError as exc:
            raise LLMError(
                f"Anthropic API-Fehler: HTTP {getattr(exc, 'status_code', 'unknown')}"
            ) from exc

    async def complete_stream(
        self, system_prompt: str, user_content: str
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """Streaming via Anthropic messages.stream(). Yields text chunks, then LLMResponse sentinel."""
        import anthropic  # noqa: PLC0415

        input_tokens = 0
        output_tokens = 0
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            ) as stream:
                async for text_chunk in stream.text_stream:
                    yield text_chunk
                # get_final_message() returns the completed message with usage data
                final_msg = await stream.get_final_message()
                if final_msg and final_msg.usage:
                    input_tokens = final_msg.usage.input_tokens or 0
                    output_tokens = final_msg.usage.output_tokens or 0
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError("Anthropic Timeout") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError("Anthropic Authentifizierung fehlgeschlagen") from exc
        except anthropic.RateLimitError as exc:
            raise LLMQuotaError("Anthropic Rate Limit oder Credits erschöpft") from exc
        except anthropic.BadRequestError as exc:
            raise LLMModelError(f"Anthropic Modell-Fehler: {self._model}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMConnectionError("Anthropic nicht erreichbar") from exc
        except anthropic.APIError as exc:
            raise LLMError(
                f"Anthropic API-Fehler: HTTP {getattr(exc, 'status_code', 'unknown')}"
            ) from exc
        # Yield usage sentinel after all text chunks
        yield LLMResponse(
            text="",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )


# ---------------------------------------------------------------------------
# Ollama Provider (via httpx, kein offizielles SDK)
# ---------------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        api_key: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        try:
            import httpx  # noqa: PLC0415

            headers: dict[str, str] = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            self._client = httpx.AsyncClient(
                base_url=base_url.rstrip("/"),
                headers=headers,
                timeout=float(timeout),
            )
        except ImportError as exc:
            raise RuntimeError(
                "httpx package nicht installiert. 'pip install httpx' ausführen."
            ) from exc
        self._model = model

    async def complete(self, system_prompt: str, user_content: str) -> LLMResponse:
        import httpx  # noqa: PLC0415 — already cached in sys.modules; needed for exception types

        try:
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            }
            response = await self._client.post("/api/chat", json=payload)
            if response.status_code in (401, 403):
                raise LLMAuthError("Ollama Authentifizierung fehlgeschlagen")
            if response.status_code == 404:
                raise LLMModelError(f"Ollama Modell nicht gefunden: {self._model}")
            response.raise_for_status()
            data = response.json()
            text = data.get("message", {}).get("content", "")
            return LLMResponse(text=text)
        except (LLMAuthError, LLMModelError):
            raise
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Ollama Timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMConnectionError("Ollama nicht erreichbar") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Ollama HTTP-Fehler: {exc.response.status_code}") from exc

    async def complete_stream(
        self, system_prompt: str, user_content: str
    ) -> AsyncGenerator[str | LLMResponse, None]:
        """Streaming via Ollama NDJSON (stream=true). Yields text chunks, then LLMResponse sentinel.

        Ollama does not report token counts in the streaming API, so the sentinel
        always has 0 input/output tokens.
        """
        import httpx  # noqa: PLC0415

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": True,
            "options": {"temperature": 0.3},
        }
        try:
            async with self._client.stream(
                "POST", "/api/chat", json=payload
            ) as response:
                try:
                    if response.status_code in (401, 403):
                        raise LLMAuthError("Ollama Authentifizierung fehlgeschlagen")
                    if response.status_code == 404:
                        raise LLMModelError(
                            f"Ollama Modell nicht gefunden: {self._model}"
                        )
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
                except (LLMAuthError, LLMModelError):
                    raise  # propagate before httpx __aexit__ can interfere
        except (LLMAuthError, LLMModelError):
            raise
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Ollama Timeout") from exc
        except httpx.ConnectError as exc:
            raise LLMConnectionError("Ollama nicht erreichbar") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Ollama HTTP-Fehler: {exc.response.status_code}") from exc
        # NOTE: The sentinel is intentionally placed OUTSIDE the try/except block.
        # On error, the exception propagates and this line is never reached — which
        # is correct: callers must not receive a sentinel after an error event.
        # On success, all text chunks have been yielded and the sentinel is safe to emit.
        # Ollama has no token data in streaming mode — sentinel always has 0 input/output tokens.
        yield LLMResponse(text="")


# ---------------------------------------------------------------------------
# LLMService — Singleton mit Provider-Fabrik
# ---------------------------------------------------------------------------


class LLMService:
    """
    Singleton-Service für LLM-basiertes Übersetzen und Optimieren.

    Initialisiert sich selbst aus `app.config.settings`.
    Wenn kein LLM konfiguriert ist, ist `is_configured()` False und
    alle Methoden werfen einen ValueError.
    """

    def __init__(self) -> None:
        self._translate_provider: Optional[LLMProvider] = None
        self._write_provider: Optional[LLMProvider] = None
        self._provider_name: str = ""
        self._display_name: str = ""
        self._translate_model: str = ""
        self._write_model: str = ""
        self._translate_prompt_template: str = ""
        self._write_prompt_template: str = ""
        self._init_from_config()

    def _init_from_config(self) -> None:
        from app.config import settings  # noqa: PLC0415 — Late import to avoid circular

        provider = (settings.llm_provider or "").strip().lower()
        if not provider:
            logger.info("Kein LLM_PROVIDER konfiguriert — LLM-Modus deaktiviert.")
            return

        api_key = (
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        )
        base_url = settings.llm_base_url
        translate_model = settings.llm_translate_model
        write_model = settings.llm_write_model
        timeout = settings.llm_timeout

        self._translate_provider, self._write_provider = self._create_providers(
            provider, api_key, base_url, translate_model, write_model, timeout
        )

        if self._translate_provider is None:
            return

        self._provider_name = provider
        self._display_name = settings.llm_display_name or provider
        self._translate_model = translate_model
        self._write_model = write_model
        self._translate_prompt_template = settings.llm_translate_prompt
        self._write_prompt_template = settings.llm_write_prompt
        logger.info(
            "LLM-Modus aktiv: provider=%s display_name=%s translate_model=%s write_model=%s timeout=%ds",
            provider,
            self._display_name,
            translate_model,
            write_model,
            timeout,
        )

    def _create_providers(
        self,
        provider: str,
        api_key: Optional[str],
        base_url: Optional[str],
        translate_model: str,
        write_model: str,
        timeout: int = 30,
    ) -> tuple[Optional[LLMProvider], Optional[LLMProvider]]:
        """Erstellt Provider-Paare (translate + write) anhand der Konfiguration."""
        try:
            if provider == "openai":
                if not api_key:
                    logger.warning(
                        "LLM_PROVIDER=openai aber LLM_API_KEY fehlt — LLM deaktiviert."
                    )
                    return None, None
                return (
                    OpenAIProvider(api_key, translate_model, base_url, timeout),
                    OpenAIProvider(api_key, write_model, base_url, timeout),
                )

            if provider == "openai-compatible":
                if not base_url:
                    logger.warning(
                        "LLM_PROVIDER=openai-compatible aber LLM_BASE_URL fehlt — LLM deaktiviert."
                    )
                    return None, None
                # The OpenAI SDK requires a non-empty string for api_key even when the
                # proxy doesn't require authentication. Use a placeholder in that case.
                effective_key = api_key or "no-key"
                return (
                    OpenAIProvider(effective_key, translate_model, base_url, timeout),
                    OpenAIProvider(effective_key, write_model, base_url, timeout),
                )

            if provider == "anthropic":
                if not api_key:
                    logger.warning(
                        "LLM_PROVIDER=anthropic aber LLM_API_KEY fehlt — LLM deaktiviert."
                    )
                    return None, None
                return (
                    AnthropicProvider(api_key, translate_model, timeout),
                    AnthropicProvider(api_key, write_model, timeout),
                )

            if provider == "ollama":
                resolved_base = base_url or "http://localhost:11434"
                return (
                    OllamaProvider(translate_model, resolved_base, api_key, timeout),
                    OllamaProvider(write_model, resolved_base, api_key, timeout),
                )

            logger.warning(
                "Unbekannter LLM_PROVIDER '%s'. Erlaubt: openai, openai-compatible, anthropic, ollama.",
                provider,
            )
            return None, None

        except RuntimeError as exc:
            logger.error("LLM-Provider konnte nicht initialisiert werden: %s", exc)
            return None, None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return self._translate_provider is not None

    async def detect_language(self, text: str, max_words: int = 50) -> Optional[str]:
        """Public API for source language detection.

        Pre-truncates text to max_words words for efficiency, then delegates to
        _detect_language(). Returns a DeepL-compatible language code or None.
        """
        words = text.split()
        truncated = " ".join(words[:max_words])
        return await self._detect_language(truncated)

    async def _detect_language(self, text: str) -> Optional[str]:
        """Erkennt die Sprache des Textes via LLM.

        Expects pre-truncated text — caller (detect_language()) is responsible
        for bounding input length before calling this private method.
        """

        system_prompt = (
            "You are a language detector. Reply with ONLY the 2-letter ISO 639-1 language code "
            "(e.g., en, de, fr, es, it, pt, ru, zh, ja, ko, ar). "
            "Do not include any other text or explanation."
        )
        user_prompt = f"What language is this text?\n\n{text}"

        try:
            result = await self._translate_provider.complete(system_prompt, user_prompt)
            # Use _normalize_lang_code for consistent resolution (handles ISO, DeepL
            # codes, region variants, and 3-letter codes)
            normalized = self._normalize_lang_code(result.text.strip())
            if normalized != "unknown":
                logger.debug(
                    "LLM detected language: %s (raw: %s)",
                    normalized,
                    result.text.strip(),
                )
                return normalized
            logger.warning(
                "LLM returned unrecognized language code: %s", result.text.strip()
            )
            return None
        except Exception as exc:
            logger.warning("Language detection failed: %s", exc)
            return None

    @staticmethod
    def _normalize_lang_code(raw: str) -> str:
        """Normalize a raw language code (from LLM) to a DeepL-compatible code.

        Handles ISO 639-1 (lowercase), uppercase DeepL codes, and common variants.
        Returns "unknown" only if nothing can be resolved.
        """
        if not raw:
            return "unknown"
        code = raw.strip().lower()
        # Direct ISO match (most common case: "en", "de", "fr", ...)
        if code in _ISO_TO_DEEPL:
            return _ISO_TO_DEEPL[code]
        # Already a valid uppercase DeepL code? ("DE", "EN", "EN-US", ...)
        upper = raw.strip().upper()
        if upper in _LANG_NAMES:
            return upper
        # Try first 2 chars (handles "en-us" → "en", "deu" → "de", etc.)
        short = code[:2]
        if short in _ISO_TO_DEEPL:
            return _ISO_TO_DEEPL[short]
        if short.upper() in _LANG_NAMES:
            return short.upper()
        logger.warning("Cannot normalize language code: %s", raw)
        return "unknown"

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def display_name(self) -> str:
        """UI-Label für den Engine-Toggle.

        Returns LLM_DISPLAY_NAME wenn gesetzt, sonst provider_name.
        Gibt einen leeren String zurück wenn LLM nicht konfiguriert ist.
        """
        return self._display_name

    @property
    def translate_model(self) -> str:
        return self._translate_model

    @property
    def write_model(self) -> str:
        return self._write_model

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
    ) -> dict:
        """
        Übersetzt `text` in `target_lang` via LLM.

        Returns:
            {"translated_text": str, "detected_source_lang": str, "usage": {"input_tokens": int, "output_tokens": int, "total_tokens": int}}
        """
        if not self._translate_provider:
            raise ValueError("LLM ist nicht konfiguriert.")

        lang_label = _lang_name(target_lang)

        logger.debug(
            "LLM translate: provider=%s model=%s target=%s chars=%d",
            self._provider_name,
            self._translate_model,
            target_lang,
            len(text),
        )

        # If source_lang is provided, use simple prompt
        if source_lang:
            system_prompt = self._translate_prompt_template.format(
                target_lang=lang_label
            )
            response = await self._translate_provider.complete(system_prompt, text)
            detected = source_lang
        else:
            # Combined prompt: translation + language detection in one LLM call
            system_prompt = (
                "You are a translation engine. "
                f"Translate the following text to {lang_label}. "
                "Respond with JSON only — no preamble, no explanation, no text before or after the JSON object: "
                '{"detected_lang": "<2-letter ISO code, e.g. en, de, fr>", "translation": "<translated text only, no added phrases>"}'
            )
            response = await self._translate_provider.complete(system_prompt, text)

            # Parse JSON response for detected_lang + translation
            try:
                # Strip markdown fences before parsing (LLMs sometimes wrap JSON)
                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```\s*$", "", raw)

                result_json = json.loads(raw)
                detected = result_json.get("detected_lang", "").strip()
                translated_text = result_json.get("translation", "").strip()
                # Normalize detected language to DeepL code
                detected = self._normalize_lang_code(detected)
                # Create new response with parsed translation
                response.text = translated_text
            except (json.JSONDecodeError, AttributeError) as exc:
                logger.warning("Failed to parse combined LLM response as JSON: %s", exc)
                # Regex fallback: try to extract detected_lang from malformed response
                lang_match = re.search(
                    r'"detected_lang"\s*:\s*"(\w{2,5})"', response.text
                )
                if lang_match:
                    detected = self._normalize_lang_code(lang_match.group(1))
                else:
                    # Last resort: use _detect_language for a separate call
                    detected = await self._detect_language(text) or "unknown"
                # Clear the unparseable blob — do not return raw JSON as translation
                response.text = ""

        # Strip markdown, then remove any LLM preamble phrases
        clean_text = _strip_meta_commentary(_strip_markdown(response.text.strip()))

        return {
            "translated_text": clean_text,
            "detected_source_lang": detected,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
            },
        }

    async def write_optimize(self, text: str, target_lang: str) -> dict:
        """
        Optimiert `text` in `target_lang` via LLM.

        Returns:
            {"optimized_text": str, "detected_lang": str, "usage": {"input_tokens": int, "output_tokens": int, "total_tokens": int}}
        """
        if not self._write_provider:
            raise ValueError("LLM ist nicht konfiguriert.")

        lang_label = _lang_name(target_lang)
        system_prompt = self._write_prompt_template.format(target_lang=lang_label)

        logger.debug(
            "LLM write_optimize: provider=%s model=%s target=%s chars=%d",
            self._provider_name,
            self._write_model,
            target_lang,
            len(text),
        )

        response = await self._write_provider.complete(system_prompt, text)

        # Strip LLM preamble phrases before any further processing
        raw_text = _strip_meta_commentary(response.text.strip())

        # Preserve paragraph breaks: replace \n\n with placeholder BEFORE markdown stripping
        PARAGRAPH_PLACEHOLDER = "\x00PARAGRAPH\x00"
        raw_text = raw_text.replace("\n\n", PARAGRAPH_PLACEHOLDER)

        # Strip any markdown formatting from the optimized text
        clean_text = _strip_markdown(raw_text.strip())

        # Restore paragraph breaks
        clean_text = clean_text.replace(PARAGRAPH_PLACEHOLDER, "\n\n")

        return {
            "optimized_text": clean_text,
            "detected_lang": target_lang,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
            },
        }

    async def debug_call(
        self,
        mode: str,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
    ) -> dict:
        """Debug-Aufruf: Gibt Prompt, Raw-Response und verarbeitete Response zurück.

        Verwendet immer non-streaming complete(), nie stream.
        Zeichnet keine Usage auf (nur für Admin-Debugging).
        """
        if not self._translate_provider:
            raise ValueError("LLM ist nicht konfiguriert.")

        lang_label = _lang_name(target_lang)

        if mode == "translate":
            provider = self._translate_provider
            model = self._translate_model

            if source_lang:
                system_prompt = self._translate_prompt_template.format(
                    target_lang=lang_label
                )
                user_content = text
            else:
                system_prompt = (
                    "You are a professional translator. "
                    f"Translate the following text to {lang_label}. "
                    "Respond with JSON only, no other text: "
                    '{"detected_lang": "<2-letter ISO code>", "translation": "<translated text>"}'
                )
                user_content = text

            response = await provider.complete(system_prompt, user_content)
            raw = response.text
            processed = _strip_markdown(raw.strip())
            detected = source_lang

            # Try to extract translation from JSON for processed field
            if not source_lang:
                try:
                    cleaned = raw.strip()
                    if cleaned.startswith("```"):
                        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
                    result_json = json.loads(cleaned)
                    detected = self._normalize_lang_code(
                        result_json.get("detected_lang", "")
                    )
                    processed = _strip_markdown(
                        result_json.get("translation", "").strip()
                    )
                except Exception as exc:
                    logger.debug("Failed to parse JSON in debug_call: %s", exc)

        else:  # write
            provider = self._write_provider
            model = self._write_model
            system_prompt = self._write_prompt_template.format(target_lang=lang_label)
            user_content = text
            response = await provider.complete(system_prompt, user_content)
            raw = response.text
            processed = _strip_markdown(raw.strip())
            detected = None

        return {
            "mode": mode,
            "provider": self._provider_name,
            "model": model,
            "system_prompt": system_prompt,
            "user_content": user_content,
            "raw_response": raw,
            "processed_response": processed,
            "strip_markdown_changed": raw.strip() != processed,
            "detected_source_lang": detected,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.total_tokens,
            },
        }

    async def _run_stream_with_detection(
        self,
        provider: LLMProvider,
        system_prompt: str,
        text: str,
        detect_task: Optional[asyncio.Task[Optional[str]]],
        known_source_lang: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Shared streaming + language-detection pattern used by translate_stream and write_optimize_stream.

        Streams chunks from *provider*, collects the LLMResponse usage sentinel,
        handles errors (cancels the detect task on failure), and finally emits a
        ``done`` event with the resolved ``detected_source_lang`` and token counts.

        Args:
            provider:          The LLMProvider whose complete_stream() is called.
            system_prompt:     The system prompt passed to complete_stream().
            text:              The user text (passed as user_content).
            detect_task:       An already-started asyncio.Task for language detection,
                               or None if detection is not needed.
            known_source_lang: If set, this value is used as detected_source_lang in
                               the done event (detect_task is still awaited/cancelled).
        """
        usage_sentinel: LLMResponse | None = None
        # First-chunk buffer: collect chunks until we have enough text to check
        # for LLM meta-preamble (e.g. "Here is the translation:"). We buffer up
        # to _PREFIX_BUFFER_LIMIT chars or until we see a newline, then strip any
        # intro phrase before flushing. After flushing, subsequent chunks stream
        # normally without buffering.
        _PREFIX_BUFFER_LIMIT = 150
        _prefix_buf: str = ""
        _prefix_flushed: bool = False
        try:
            async for chunk in provider.complete_stream(system_prompt, text):
                # The last item yielded by complete_stream() is an LLMResponse sentinel
                # carrying token usage data. Skip it here; collect it for the done event.
                if isinstance(chunk, LLMResponse):
                    usage_sentinel = chunk
                    continue
                # Use _strip_markdown_chunk() (not _strip_markdown()) to preserve
                # leading/trailing whitespace that represents word boundaries between chunks.
                clean_chunk = _strip_markdown_chunk(chunk)  # type: str

                if not _prefix_flushed:
                    _prefix_buf += clean_chunk
                    # Flush once we have enough content or hit a newline boundary
                    if len(_prefix_buf) >= _PREFIX_BUFFER_LIMIT or "\n" in _prefix_buf:
                        _prefix_buf = _strip_meta_commentary(_prefix_buf)
                        _prefix_flushed = True
                        if _prefix_buf:
                            yield f"data: {json.dumps({'chunk': _prefix_buf})}\n\n"
                else:
                    yield f"data: {json.dumps({'chunk': clean_chunk})}\n\n"
        except Exception as exc:
            # Flush any buffered prefix before reporting error
            if not _prefix_flushed and _prefix_buf:
                _prefix_buf = _strip_meta_commentary(_prefix_buf)
                if _prefix_buf:
                    yield f"data: {json.dumps({'chunk': _prefix_buf})}\n\n"
            logger.error("LLM streaming error: %s", exc)
            if detect_task and not detect_task.done():
                detect_task.cancel()
                # Await after cancel to prevent dangling coroutines.
                # CancelledError is a BaseException (not Exception) in Python 3.8+.
                try:
                    await detect_task
                except (asyncio.CancelledError, Exception):
                    pass
            yield f"data: {json.dumps({'error': _safe_stream_error_msg(exc)})}\n\n"
            return

        # Flush prefix buffer if stream ended before hitting the size threshold
        # (e.g. very short translations that never reached _PREFIX_BUFFER_LIMIT)
        if not _prefix_flushed and _prefix_buf:
            _prefix_buf = _strip_meta_commentary(_prefix_buf)
            if _prefix_buf:
                yield f"data: {json.dumps({'chunk': _prefix_buf})}\n\n"

        # Resolve detected language from task result or known value
        if known_source_lang:
            detected = known_source_lang
        elif detect_task:
            try:
                detected = await detect_task or "unknown"
            except Exception as exc:
                logger.warning("Parallel language detection failed: %s", exc)
                detected = "unknown"
        else:
            detected = "unknown"

        done_event: dict = {"done": True, "detected_source_lang": detected}
        if usage_sentinel:
            done_event["input_tokens"] = usage_sentinel.input_tokens
            done_event["output_tokens"] = usage_sentinel.output_tokens
        yield f"data: {json.dumps(done_event)}\n\n"

    async def translate_stream(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming-Variante von translate().

        Yields SSE-formatted lines:
          data: {"chunk": "<text>"}\n\n
          data: {"done": true, "detected_source_lang": "<code>"}\n\n
          data: {"error": "<message>"}\n\n   (on error)
        """
        if not self._translate_provider:
            raise ValueError("LLM ist nicht konfiguriert.")

        lang_label = _lang_name(target_lang)
        system_prompt = self._translate_prompt_template.format(target_lang=lang_label)

        logger.debug(
            "LLM translate_stream: provider=%s model=%s target=%s chars=%d",
            self._provider_name,
            self._translate_model,
            target_lang,
            len(text),
        )

        # Fire language detection in parallel when source is unknown.
        # Result is ready by the time the stream completes.
        detect_task: Optional[asyncio.Task] = None
        if not source_lang:
            detect_task = asyncio.create_task(self._detect_language(text))

        async for event in self._run_stream_with_detection(
            self._translate_provider, system_prompt, text, detect_task, source_lang
        ):
            yield event

    async def write_optimize_stream(
        self,
        text: str,
        target_lang: str,
    ) -> AsyncGenerator[str, None]:
        """Streaming-Variante von write_optimize().

        Detects the source language in parallel with streaming so the caller
        knows which language was optimised.

        Yields SSE-formatted lines:
          data: {"chunk": "<text>"}                             — incremental chunk
          data: {"done": true, "detected_source_lang": "<code>"}  — final event
          data: {"error": "<message>"}                          — on error
        """
        if not self._write_provider:
            raise ValueError("LLM ist nicht konfiguriert.")

        lang_label = _lang_name(target_lang)
        system_prompt = self._write_prompt_template.format(target_lang=lang_label)

        logger.debug(
            "LLM write_optimize_stream: provider=%s model=%s target=%s chars=%d",
            self._provider_name,
            self._write_model,
            target_lang,
            len(text),
        )

        # Detect source language in parallel with the stream so the done-event
        # can include it. Language detection uses _translate_provider.
        detect_task: Optional[asyncio.Task] = None
        if self._translate_provider:
            detect_task = asyncio.create_task(self._detect_language(text))

        async for event in self._run_stream_with_detection(
            self._write_provider, system_prompt, text, detect_task
        ):
            yield event


# Singleton — wird beim Modulimport einmalig initialisiert
llm_service = LLMService()
