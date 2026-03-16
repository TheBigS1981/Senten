from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Supported DeepL target languages
# ---------------------------------------------------------------------------
# Full list of languages supported by DeepL as of early 2025.
# Source: https://www.deepl.com/docs-api/translate-text/translate-text/

DEEPL_TARGET_LANGUAGES = {
    "AR": "Arabisch",
    "BG": "Bulgarisch",
    "CS": "Tschechisch",
    "DA": "Dänisch",
    "DE": "Deutsch",
    "EL": "Griechisch",
    "EN-GB": "Englisch (UK)",
    "EN-US": "Englisch (US)",
    "ES": "Spanisch",
    "ET": "Estnisch",
    "FI": "Finnisch",
    "FR": "Französisch",
    "HU": "Ungarisch",
    "ID": "Indonesisch",
    "IT": "Italienisch",
    "JA": "Japanisch",
    "KO": "Koreanisch",
    "LT": "Litauisch",
    "LV": "Lettisch",
    "NB": "Norwegisch",
    "NL": "Niederländisch",
    "PL": "Polnisch",
    "PT-BR": "Portugiesisch (BR)",
    "PT-PT": "Portugiesisch (PT)",
    "RO": "Rumänisch",
    "RU": "Russisch",
    "SK": "Slowakisch",
    "SL": "Slowenisch",
    "SV": "Schwedisch",
    "TR": "Türkisch",
    "UK": "Ukrainisch",
    "ZH": "Chinesisch (vereinfacht)",
    "ZH-HANS": "Chinesisch (vereinfacht)",
    "ZH-HANT": "Chinesisch (traditionell)",
}

DEEPL_PREFERRED_TARGETS = ["DE", "EN-US"]

DEEPL_SOURCE_LANGUAGES = {
    "AR": "Arabisch",
    "BG": "Bulgarisch",
    "CS": "Tschechisch",
    "DA": "Dänisch",
    "DE": "Deutsch",
    "EL": "Griechisch",
    "EN": "Englisch",
    "ES": "Spanisch",
    "ET": "Estnisch",
    "FI": "Finnisch",
    "FR": "Französisch",
    "HU": "Ungarisch",
    "ID": "Indonesisch",
    "IT": "Italienisch",
    "JA": "Japanisch",
    "KO": "Koreanisch",
    "LT": "Litauisch",
    "LV": "Lettisch",
    "NB": "Norwegisch",
    "NL": "Niederländisch",
    "PL": "Polnisch",
    "PT": "Portugiesisch",
    "RO": "Rumänisch",
    "RU": "Russisch",
    "SK": "Slowakisch",
    "SL": "Slowenisch",
    "SV": "Schwedisch",
    "TR": "Türkisch",
    "UK": "Ukrainisch",
    "ZH": "Chinesisch",
}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    target_lang: str = Field(default="DE")
    source_lang: Optional[str] = Field(default=None)
    engine: Literal["deepl", "llm"] = Field(default="deepl")

    model_config = ConfigDict(str_strip_whitespace=True)


class TranslateResponse(BaseModel):
    translated_text: str
    detected_source_lang: Optional[str] = None
    characters_used: int
    usage: Optional[dict[str, int]] = None


class WriteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    target_lang: str = Field(default="DE")
    engine: Literal["deepl", "llm"] = Field(default="deepl")

    model_config = ConfigDict(str_strip_whitespace=True)


class WriteResponse(BaseModel):
    optimized_text: str
    characters_used: int
    usage: Optional[dict[str, int]] = None


class UsageStats(BaseModel):
    daily_translate: int = 0
    daily_write: int = 0
    daily_total: int = 0
    monthly_translate: int = 0
    monthly_write: int = 0
    monthly_total: int = 0
    monthly_limit: int
    remaining: int
    percent_used: float
    deepl_character_count: Optional[int] = None
    deepl_character_limit: Optional[int] = None


class UsageRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    characters_used: int
    operation_type: str
    target_language: Optional[str]
    created_at: datetime


class HistoryRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    operation_type: str
    source_text: str
    target_text: str
    source_lang: Optional[str]
    target_lang: str
    created_at: datetime


class HistoryListResponse(BaseModel):
    records: list[HistoryRecordResponse]
    total: int
    limit: int
    offset: int


class HistoryCreateRequest(BaseModel):
    operation_type: str = Field(..., pattern="^(translate|write)$")
    source_text: str = Field(..., min_length=1, max_length=10000)
    target_text: str = Field(..., min_length=1, max_length=10000)
    source_lang: Optional[str] = Field(default=None, max_length=10)
    target_lang: str = Field(..., max_length=10)

    model_config = ConfigDict(str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# User management schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)
    remember_me: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class UserSettingsSchema(BaseModel):
    """Partial update — all fields optional."""

    theme: Optional[str] = Field(default=None, pattern=r"^(light|dark)-(blue|violet)$")
    accent_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$|^$")
    source_lang: Optional[str] = Field(default=None, max_length=10)
    target_lang: Optional[str] = Field(default=None, max_length=10)
    engine_translate: Optional[str] = Field(default=None, pattern=r"^(deepl|llm)$")
    engine_write: Optional[str] = Field(default=None, pattern=r"^(deepl|llm)$")
    diff_view: Optional[bool] = None
    ui_language: Optional[str] = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")

    model_config = ConfigDict(str_strip_whitespace=True)


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    theme: str
    accent_color: Optional[str]
    source_lang: Optional[str]
    target_lang: str
    engine_translate: str
    engine_write: str
    diff_view: bool
    ui_language: str
    updated_at: datetime


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: Optional[str]
    is_admin: bool
    auth_provider: str
    last_login_at: Optional[datetime]
    avatar_url: str
    settings: UserSettingsResponse


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: Optional[str]
    is_admin: bool
    is_active: bool
    auth_provider: str
    last_login_at: Optional[datetime]
    created_at: datetime
    avatar_url: str


_EMAIL_PATTERN = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"


class AdminUserCreateRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.\-]+$"
    )
    password: str = Field(..., min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254, pattern=_EMAIL_PATTERN)
    is_admin: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminUserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    display_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=254, pattern=_EMAIL_PATTERN)

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class LLMDebugRequest(BaseModel):
    mode: Literal["translate", "write"]
    text: str = Field(..., min_length=1, max_length=10000)
    target_lang: str = Field(default="DE")
    source_lang: Optional[str] = Field(default=None)

    model_config = ConfigDict(str_strip_whitespace=True)


class LLMDebugResponse(BaseModel):
    mode: str
    provider: str
    model: str
    system_prompt: str
    user_content: str
    raw_response: str
    processed_response: str
    strip_markdown_changed: bool
    detected_source_lang: Optional[str]
    usage: dict[str, int]


class DetectLangRequest(BaseModel):
    """Request body for POST /api/detect-lang.

    Designed for short snippets (first 50 words of the source text) —
    max_length=500 is generous for that purpose.
    """

    text: str = Field(..., min_length=1, max_length=500)
    max_words: int = Field(default=50, ge=1, le=200)


class DetectLangResponse(BaseModel):
    """Response for POST /api/detect-lang.

    detected_lang: DeepL language code (e.g. "DE", "EN-US") or "unknown"
                   when detection failed or LLM is not configured.
    """

    detected_lang: str


# ---------------------------------------------------------------------------
# i18n schemas
# ---------------------------------------------------------------------------


class TranslationCatalog(BaseModel):
    """Full translation catalog for a language."""

    lang: str
    translations: dict[str, str]


class LanguageInfo(BaseModel):
    """Information about a supported UI language."""

    code: str
    name: str  # Localized name (e.g., "Deutsch" for German)
    native_name: str  # Native name (e.g., "Deutsch")


class LanguageListResponse(BaseModel):
    """List of supported UI languages."""

    languages: list[LanguageInfo]
    default: str
