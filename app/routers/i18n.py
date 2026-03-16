"""i18n API endpoints for translations and language information."""

import logging

from fastapi import APIRouter

from app.models.schemas import LanguageInfo, LanguageListResponse, TranslationCatalog
from app.services import i18n_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/i18n/languages", response_model=LanguageListResponse)
async def get_languages():
    """Return list of supported UI languages with localized names."""
    languages = [
        LanguageInfo(
            code=lang["code"],
            name=lang["name"],
            native_name=lang["native_name"],
        )
        for lang in i18n_service.get_supported_languages()
    ]
    return LanguageListResponse(
        languages=languages,
        default=i18n_service.get_default_language(),
    )


@router.get("/i18n/{lang}", response_model=TranslationCatalog)
async def get_translations(lang: str):
    """Return the full translation catalog for the specified language.

    Falls back to English if the requested language is not available.
    """
    if not i18n_service.is_supported(lang):
        # Still return translations - service handles fallback
        logger.info("Unsupported language requested: %s, falling back to default", lang)

    translations = i18n_service.get_translations(lang)
    return TranslationCatalog(
        lang=lang,
        translations=translations,
    )
