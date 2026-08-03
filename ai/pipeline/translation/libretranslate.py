import requests

from translation.base import TranslationProvider


class LibreTranslateProvider(TranslationProvider):
    name = "libretranslate"

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.server_url}/languages", timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def translate(self, text: str, target_language: str) -> str:
        response = requests.post(
            f"{self.server_url}/translate",
            json={
                "q": text,
                "source": "auto",
                "target": target_language,
                "format": "text",
            },
            timeout=30,
        )
        response.raise_for_status()
        translated = response.json().get("translatedText")
        if not translated:
            raise RuntimeError(f"LibreTranslate returned no translated text for {target_language}")
        return translated
