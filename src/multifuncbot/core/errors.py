"""Expected domain failures, safe to translate at the transport boundary."""


class DomainError(ValueError):
    def __init__(self, ru: str, en: str):
        super().__init__(en)
        self.ru = ru
        self.en = en

    def message(self, language: str) -> str:
        return self.ru if language == "ru" else self.en
