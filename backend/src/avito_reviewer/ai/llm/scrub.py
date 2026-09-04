"""Обезличивание перед отправкой наружу.

Здесь сейчас базовый слой: регулярки по контактам и идентификаторам плюс
метаданные git. Полный контур из архитектуры — NER на локальной модели,
код-специфика, валидатор остаточного риска — отдельный модуль, который
встанет на это же место.

Принципиальное решение уже здесь: **псевдонимизация, а не вырезание**.
Модель должна видеть, что `[PERSON_1]` в README и `[PERSON_1]` в комментарии
к коду — один человек, иначе разбор теряет связность. Обратная карта живёт
ровно столько, сколько идёт запрос, и наружу не уходит.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Порядок важен: сначала длинные и специфичные шаблоны, потом общие.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+7|8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("TELEGRAM", re.compile(r"(?<![\w/])@[A-Za-z][A-Za-z0-9_]{4,31}\b")),
    ("SNILS", re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}[\s-]\d{2}(?!\d)")),
    ("INN", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("PASSPORT", re.compile(r"(?<!\d)\d{4}\s?\d{6}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d{4}[\s-]?){3}\d{4}(?!\d)")),
    ("URL_PROFILE", re.compile(r"https?://(?:t\.me|vk\.com|linkedin\.com)/\S+")),
]


@dataclass
class ScrubResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # токен -> исходное значение
    redactions: int = 0

    def rehydrate(self, text: str) -> str:
        """Вернуть настоящие значения. Только внутри периметра."""
        for token, original in self.mapping.items():
            text = text.replace(token, original)
        return text


class Scrubber:
    """Псевдонимизатор с устойчивыми токенами в пределах одного запроса."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._seen: dict[str, str] = {}

    def _token_for(self, kind: str, value: str) -> str:
        key = f"{kind}:{value.lower()}"
        if key not in self._seen:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            self._seen[key] = f"[{kind}_{self._counters[kind]}]"
        return self._seen[key]

    def scrub(self, text: str) -> ScrubResult:
        mapping: dict[str, str] = {}
        redactions = 0

        for kind, pattern in PATTERNS:
            def replace(match: re.Match[str]) -> str:
                nonlocal redactions
                original = match.group(0)
                token = self._token_for(kind, original)
                mapping[token] = original
                redactions += 1
                return token

            text = pattern.sub(replace, text)

        return ScrubResult(text=text, mapping=mapping, redactions=redactions)


HIGH_CONFIDENCE_LEFTOVERS = [
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+7|8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"),
]


def residual_risk(text: str) -> list[str]:
    """Второй проход по уже очищенному тексту.

    Если после скраба что-то осталось, маршрут понижается до локального.
    Ошибка в сторону «не отправили» дешевле ошибки в сторону «отправили».
    """
    found: list[str] = []
    for pattern in HIGH_CONFIDENCE_LEFTOVERS:
        found.extend(pattern.findall(text))
    return found
