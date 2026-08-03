from translation.base import TranslationProvider
from translation.libretranslate import LibreTranslateProvider


def configured_provider(settings: dict) -> TranslationProvider | None:
    provider_name = settings.get("translationProvider", "libretranslate")

    if provider_name == "libretranslate":
        return LibreTranslateProvider(
            settings.get("libreTranslateUrl", "http://localhost:5000")
        )

    return None
