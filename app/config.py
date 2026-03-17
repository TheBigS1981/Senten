import logging
import os
import secrets
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = Path(__file__).parent.parent.resolve()

VERSION = "1.0.0"


@lru_cache(maxsize=1)
def get_git_info() -> Tuple[Optional[str], bool]:
    """
    Get git commit hash and whether this is a dev build.

    Returns:
        Tuple of (commit_hash, is_dev_build)
        - commit_hash: Short hash (7 chars) or None if not a git repo / on release tag
        - is_dev_build: True if not on an exact tag (dev mode)
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return None, False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            return commit_hash, True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None, False


def _get_secret_key() -> str:
    """Get SECRET_KEY from environment or generate a warning for development."""
    secret_key = os.environ.get("SECRET_KEY")
    if secret_key:
        return secret_key

    # Auto-generated key for development only - warn users
    logger.warning(
        "SECRET_KEY not set - using auto-generated key (not suitable for production). "
        "Set SECRET_KEY in environment or .env file for production use."
    )
    return secrets.token_hex(32)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepL API — optional so mock mode is reachable when key is missing
    deepl_api_key: Optional[SecretStr] = None

    # OIDC authentication — all optional
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[SecretStr] = None

    # HTTP Basic Auth fallback (used when OIDC is not configured)
    auth_username: Optional[str] = None
    auth_password: Optional[SecretStr] = None

    # User management
    allow_anonymous: bool = True  # Allow unauthenticated access (no login required)
    admin_username: Optional[str] = (
        None  # Initial admin username (created on first start)
    )
    admin_password: Optional[SecretStr] = None  # Initial admin password
    session_lifetime_hours: int = Field(
        default=168, ge=1
    )  # Session duration in hours (7 days)
    session_lifetime_remember_hours: int = Field(
        default=720, ge=1
    )  # "Remember me" session duration (default: 30 days)

    # Application
    secret_key: str = _get_secret_key()
    database_url: str = f"sqlite:///{PROJECT_DIR}/data/senten.db"
    monthly_char_limit: int = 500000

    # Security
    trusted_proxies: list[str] = Field(default=["127.0.0.1", "::1"])
    session_cookie_secure: bool = True
    is_production: bool = Field(default=True)

    # Rate limiting (applied to translate and write endpoints)
    # Requests per minute - defaults allow reasonable usage
    rate_limit_per_minute: int = 30
    # Burst limit for short spikes
    rate_limit_burst: int = 10

    # CORS — restrict to known origins in production (comma-separated list)
    allowed_origins: str = ""

    # LLM — all optional; if LLM_PROVIDER is not set, LLM mode is disabled
    llm_provider: Optional[str] = (
        None  # openai | anthropic | ollama | openai-compatible
    )
    llm_api_key: Optional[SecretStr] = None  # optional for Ollama and openai-compatible
    llm_base_url: Optional[str] = (
        None  # required for Ollama + openai-compatible, optional for plain OpenAI
    )
    llm_translate_model: str = "gpt-4o"
    llm_write_model: str = "gpt-4o"
    llm_display_name: Optional[str] = None  # UI label in engine toggle, e.g. "LiteLLM"
    llm_timeout: int = Field(default=30, ge=1)  # seconds; applies to all LLM providers
    llm_max_input_chars: int = Field(
        default=5000, ge=1
    )  # max chars per LLM request (cost guard)
    llm_translate_prompt: str = (
        "You are a translation engine. Output ONLY the translated text. Nothing else.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚨 ABSOLUTELY FORBIDDEN — YOUR OUTPUT WILL BE REJECTED IF YOU USE THESE:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "❌ NO introductory phrases — e.g. 'Here is the translation:', 'Certainly!',\n"
        "   'Sure!', 'Here's the translated text:', 'Translation:', 'Of course!' etc.\n"
        "❌ NO closing remarks, notes, or commentary after the translation\n"
        "❌ NO content that was not present in the original text\n"
        "❌ NO markdown formatting of any kind\n"
        "❌ NO **bold** text (asterisks)\n"
        "❌ NO *italic* text (underscores or asterisks)\n"
        "❌ NO # headings (# Heading, ## Heading, etc.)\n"
        "❌ NO bullet points or numbered lists (- item, 1. item)\n"
        "❌ NO code blocks (```code```)\n"
        "❌ NO inline code (`code`)\n"
        "❌ NO links ([text](url))\n"
        "❌ NO blockquotes (> quote)\n"
        "❌ NO tables (| col | col |)\n"
        "❌ NO horizontal rules (---)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ REQUIRED — CORRECT OUTPUT FORMAT:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Output MUST be plain text only — just words and punctuation\n"
        "• Start directly with the first translated word — no preamble whatsoever\n"
        "• Every word MUST be separated by a single space\n"
        "• NEVER concatenate words together\n"
        '   - WRONG:  "Stuttgart\'sMost Beautiful"  → CORRECT:  "Stuttgart\'s Most Beautiful"\n'
        '   - WRONG:  "Buildings:18"                → CORRECT:  "Buildings: 18"\n'
        '   - WRONG:  "inStuttgart"                 → CORRECT:  "in Stuttgart"\n'
        '   - WRONG:  "Diesistfalsch"               → CORRECT:  "Dies ist falsch"\n'
        "• Return ONLY the translated text — no quotes, no explanations, no notes\n"
        "• Your output is injected directly into a UI — any meta-text will be shown to the user\n\n"
        "Translate to {target_lang}:"
    )
    llm_write_prompt: str = (
        "You are a text editor. Output ONLY the improved text. Nothing else.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚨 ABSOLUTELY FORBIDDEN — YOUR OUTPUT WILL BE REJECTED IF YOU USE THESE:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "❌ NO introductory phrases — e.g. 'Here is the improved text:', 'Certainly!',\n"
        "   'Sure!', 'Here's the optimized version:', 'Of course!' etc.\n"
        "❌ NO closing remarks, notes, or commentary about your changes\n"
        "❌ NO content that was not present in the original text\n"
        "❌ NO markdown formatting of any kind\n"
        "❌ NO **bold** text (asterisks)\n"
        "❌ NO *italic* text (underscores or asterisks)\n"
        "❌ NO # headings (# Heading, ## Heading, etc.)\n"
        "❌ NO bullet points or numbered lists (- item, 1. item)\n"
        "❌ NO code blocks (```code```)\n"
        "❌ NO inline code (`code`)\n"
        "❌ NO links ([text](url))\n"
        "❌ NO blockquotes (> quote)\n"
        "❌ NO tables (| col | col |)\n"
        "❌ NO horizontal rules (---)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ REQUIRED — CORRECT OUTPUT FORMAT:\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Output MUST be plain text only — just words and punctuation\n"
        "• Start directly with the first word of the improved text — no preamble\n"
        "• Every word MUST be separated by a single space\n"
        "• NEVER concatenate words together\n"
        '   - WRONG:  "Stuttgart\'sMost Beautiful"  → CORRECT:  "Stuttgart\'s Most Beautiful"\n'
        '   - WRONG:  "Buildings:18"                → CORRECT:  "Buildings: 18"\n'
        '   - WRONG:  "inStuttgart"                 → CORRECT:  "in Stuttgart"\n'
        '   - WRONG:  "Diesistfalsch"               → CORRECT:  "Dies ist falsch"\n'
        "• Return ONLY the improved text — no quotes, no explanations, no notes\n"
        "• Your output is injected directly into a UI — any meta-text will be shown to the user\n\n"
        "Improve the following text in {target_lang}:"
    )


settings = Settings()
