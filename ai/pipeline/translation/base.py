from abc import ABC, abstractmethod


class TranslationProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def translate(self, text: str, target_language: str) -> str:
        pass
