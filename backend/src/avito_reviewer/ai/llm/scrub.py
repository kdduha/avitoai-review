"""Обезличивание перед отправкой наружу.

Три слоя в порядке убывания надёжности.

**Известные личности.** В бандле лежит `StudentRef` с логинами, имена приходят
от платформы. Вычищаются точно, вместе с падежами фамилии, инициалами, логином
внутри путей импорта и локальной частью почты.

**Имена, которых мы не знаем** — соавтор, преподаватель, коллега из чата. Ловят
детерминированные признаки русского ФИО: отчество (`-ович`, `-евна`, `-инична`)
и маркеры «Автор:», «Выполнил:», «Проверил:». Только кириллица: латиница в коде
— это идентификаторы, и трогать их значит ломать разбор.

**Контакты и номера.** Почта, телефон, телеграм, СНИЛС, ИНН, паспорт, карта.

Псевдонимизация, а не вырезание: модель должна видеть, что `[STUDENT]` в README
и `[STUDENT]` в комментарии к коду — один человек. Обратная карта живёт ровно
столько, сколько идёт запрос, и наружу не уходит.

Морфология словарём не читается, NER не запускается (`TaskKind.NER` заперт в
локальный маршрут, самой модели нет). До тех пор `residual_risk` сообщает о том,
что осталось похожим на имя, и маршрут понижается.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Порядок важен: сначала длинные и специфичные шаблоны, потом общие.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+7|8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("TELEGRAM", re.compile(
        r"(?<![\w/])@(?!author|param|return|throws|see|deprecated|override|inheritDoc)"
        r"[A-Za-z][A-Za-z0-9_]{4,31}\b",
        re.I,
    )),
    ("SNILS", re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}[\s-]\d{2}(?!\d)")),
    ("INN", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("PASSPORT", re.compile(r"(?<!\d)\d{4}\s?\d{6}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d{4}[\s-]?){3}\d{4}(?!\d)")),
    ("URL_PROFILE", re.compile(r"https?://(?:t\.me|vk\.com|linkedin\.com)/\S+")),
]

_WORD = r"[А-ЯЁ][а-яё]+"

# Отчество — самый специфичный признак русского ФИО: по нему можно забирать
# соседние слова целиком.
PATRONYMIC = r"[А-ЯЁ][а-яё]+(?:ович|овича|овичу|овичем|евич|евича|евичу|евичем|ьич|ича|овна|овны|овне|овну|овной|евна|евны|евне|евну|евной|инична|иничны)"

NAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # «Улитин Пётр Валерьевич», «Пётр Валерьевич Улитин»
    ("PERSON", re.compile(rf"\b{_WORD}[ \t]+{_WORD}[ \t]+{PATRONYMIC}\b")),
    ("PERSON", re.compile(rf"\b{_WORD}[ \t]+{PATRONYMIC}\b")),
    ("PERSON", re.compile(rf"\b{PATRONYMIC}[ \t]+{_WORD}\b")),
    # «Улитин П. В.», «Улитин П.»
    ("PERSON", re.compile(rf"\b{_WORD}[ \t]+[А-ЯЁ]\.(?:[ \t]*[А-ЯЁ]\.)?")),
    ("PERSON", re.compile(rf"\b[А-ЯЁ]\.(?:[ \t]*[А-ЯЁ]\.)?[ \t]*{_WORD}\b")),
]

# Два слова с заглавных подряд в одной строке. Замер на 7938 словах реального
# технического текста: три срабатывания, два из них — настоящее имя.
CAPITALIZED_PAIR = re.compile(rf"(?<![.!?]\s)\b{_WORD}[ \t]+{_WORD}\b")

# Явные маркеры авторства: то, что стоит после них, — имя, даже если отчества нет.
AUTHOR_MARKER = re.compile(
    r"(?P<marker>\b(?:Автор|Авторы|Студент|Студентка|Выполнил|Выполнила|Выполнено|Сдал|Сдала|"
    r"Проверил|Проверила|Ревьюер|Куратор|Преподаватель|Наставник|Ментор|Author|Student)\b[ \t]*[:—–-]?[ \t]*)"
    rf"(?P<name>{_WORD}(?:[ \t]+{_WORD}){{0,2}}|[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){{0,2}})"
)

# Хвосты окончаний для склонения. Морфологию словарём не читаем: ошибка в
# сторону лишней замены дешевле.
_ENDINGS = ("", "а", "ы", "у", "е", "ом", "ым", "ой", "ей", "и", "я", "ю", "ём", "ев", "ева")

# Код-специфика: владелец пометки и подпись коммита. Логин стоит здесь по
# конвенции, поэтому ловится и незнакомый — в бандле лежит только логин сдававшего.
CODE_OWNER = re.compile(
    r"(?P<marker>\b(?:TODO|FIXME|HACK|XXX|NOTE)[ \t]*\()(?P<name>[\w.@-]{3,})(?=\))", re.I
)
AUTHOR_TAG = re.compile(
    r"(?P<marker>(?:@author|Signed-off-by|Co-authored-by|Reviewed-by)[ \t]*:?[ \t]*)(?P<name>[^\n<]{2,58}[^\s<])", re.I
)

STUDENT_ID = re.compile(r"\b(?:студенческий[ \t]+билет|зачётка|зачетка|студ\.?[ \t]*билет)[ \t]*№?[ \t]*\d+", re.I)


@dataclass(frozen=True)
class Identity:
    """Тот, чья личность известна системе до разбора.

    Имя приходит не из бандла: `StudentRef` намеренно его не хранит. Его
    подставляет платформа, когда знает; без имени остаются логины, и это уже
    закрывает пути импорта вида `github.com/student-1043/...`.
    """

    role: str = "person"
    name: str | None = None
    handles: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()

    @property
    def token(self) -> str:
        return f"[{self.role.upper()}]"

    @property
    def handle_token(self) -> str:
        return f"[{self.role.upper()}_HANDLE]"

    @property
    def email_token(self) -> str:
        return f"[{self.role.upper()}_EMAIL]"


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


def _variants(word: str) -> str:
    """Регулярка на слово со всеми ходовыми падежными окончаниями."""
    stem = word.rstrip("аеёиоуыэюя") if len(word) > 4 else word
    tails = "|".join(sorted((re.escape(e) for e in _ENDINGS if e), key=len, reverse=True))
    return rf"{re.escape(stem)}(?:{tails})?"


def _identity_patterns(identity: Identity) -> list[tuple[str, re.Pattern[str]]]:
    """Точные шаблоны на известного человека — самый надёжный слой скраба."""
    out: list[tuple[str, re.Pattern[str]]] = []

    for handle in identity.handles:
        if len(handle) < 3:
            continue
        # Логин встречается и сам по себе, и внутри пути импорта каждого файла.
        out.append((identity.handle_token, re.compile(rf"(?<![\w-]){re.escape(handle)}(?![\w-])", re.I)))

    for email in identity.emails:
        out.append((identity.email_token, re.compile(re.escape(email), re.I)))
        local = email.split("@")[0]
        if len(local) >= 4:
            out.append((identity.handle_token, re.compile(rf"(?<![\w.]){re.escape(local)}(?![\w@])", re.I)))

    if identity.name:
        parts = [p for p in re.split(r"\s+", identity.name.strip()) if p]
        if len(parts) >= 2:
            # Сначала самая длинная форма, иначе она распадётся на куски.
            out.append((identity.token, re.compile(rf"\b{re.escape(identity.name)}\b")))
            surname, given = parts[0], parts[1]
            out.append((identity.token, re.compile(rf"\b{_variants(surname)}[ \t]+{_variants(given)}\b")))
            out.append((identity.token, re.compile(rf"\b{_variants(given)}[ \t]+{_variants(surname)}\b")))
            out.append((identity.token, re.compile(rf"\b{_variants(surname)}[ \t]+[А-ЯЁ]\.(?:[ \t]*[А-ЯЁ]\.)?")))
        for part in parts:
            if len(part) >= 4:
                out.append((identity.token, re.compile(rf"\b{_variants(part)}\b")))
    return out


class Scrubber:
    """Псевдонимизатор с устойчивыми токенами в пределах одного запроса."""

    def __init__(self, identities: Sequence[Identity] = ()) -> None:
        self._counters: dict[str, int] = {}
        self._seen: dict[str, str] = {}
        self.identities = tuple(identities)

    def _token_for(self, kind: str, value: str) -> str:
        if kind.startswith("["):  # токен известной личности задан заранее
            return kind
        key = f"{kind}:{value.lower()}"
        if key not in self._seen:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            self._seen[key] = f"[{kind}_{self._counters[kind]}]"
        return self._seen[key]

    def scrub(self, text: str) -> ScrubResult:
        mapping: dict[str, str] = {}
        redactions = 0

        def apply(kind: str, pattern: re.Pattern[str], value_group: str | None = None) -> None:
            nonlocal text, redactions

            def replace(match: re.Match[str]) -> str:
                nonlocal redactions
                original = match.group(value_group) if value_group else match.group(0)
                if original.startswith("["):
                    return match.group(0)
                token = self._token_for(kind, original)
                mapping.setdefault(token, original)
                redactions += 1
                if value_group:
                    return match.group("marker") + token
                return token

            text = pattern.sub(replace, text)

        # 1. Известные личности — точно и первыми.
        for identity in self.identities:
            for kind, pattern in _identity_patterns(identity):
                apply(kind, pattern)

        # 2. Код-специфика и подписи: конструкция известна целиком, поэтому идёт
        #    до общих шаблонов — иначе «@author» уходит в правило телеграма.
        apply("HANDLE", CODE_OWNER, value_group="name")
        apply("PERSON", AUTHOR_TAG, value_group="name")
        apply("PERSON", AUTHOR_MARKER, value_group="name")

        # 3. Контакты и номера.
        for kind, pattern in PATTERNS:
            apply(kind, pattern)

        # 4. Имена, которых мы не знали.
        for kind, pattern in NAME_PATTERNS:
            apply(kind, pattern)
        apply("PERSON", CAPITALIZED_PAIR)
        apply("STUDENT_ID", STUDENT_ID)

        return ScrubResult(text=text, mapping=mapping, redactions=redactions)


HIGH_CONFIDENCE_LEFTOVERS: list[tuple[str, re.Pattern[str]]] = [
    ("почта", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("телефон", re.compile(r"(?<!\d)(?:\+7|8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("отчество", re.compile(rf"\b{PATRONYMIC}\b")),
    ("имя после маркера авторства", AUTHOR_MARKER),
    ("похоже на имя", CAPITALIZED_PAIR),
    ("владелец пометки в коде", CODE_OWNER),
    ("подпись автора", AUTHOR_TAG),
]


def residual_risk(text: str, identities: Iterable[Identity] = ()) -> list[str]:
    """Второй проход по уже очищенному тексту.

    Если после скраба что-то осталось, маршрут понижается до локального.
    Ошибка в сторону «не отправили» дешевле ошибки в сторону «отправили».

    Проверять здесь ровно то же, что вычищал скрабер, — не дублирование, а
    смысл валидатора: он ловит случай, когда шаблон не сработал, а отчёт
    сказал «заменено N». Отчёт без проверки хуже отсутствия отчёта.
    """
    found: list[str] = []

    for identity in identities:
        for _, pattern in _identity_patterns(identity):
            match = pattern.search(text)
            if match and not match.group(0).startswith("["):
                found.append(f"{identity.role}: {match.group(0)[:40]}")

    for label, pattern in HIGH_CONFIDENCE_LEFTOVERS:
        for match in pattern.finditer(text):
            fragment = match.group("name") if "name" in (match.groupdict() or {}) else match.group(0)
            if not fragment.startswith("["):
                found.append(f"{label}: {fragment[:40]}")
    return found
