"""Классификация фрагментов моделью.

Единственный сигнал ансамбля, который ходит наружу, и к нему то же
требование, что к ревью-агенту: **цитата обязательна**. Ответ без дословного
фрагмента отбрасывается целиком — иначе получается «модель считает, что это
сгенерировано», а показать ревьюеру нечего.

Отдельно исключается шаблонный код. Без allowlist детектор уверенно ловит
`go.sum`, миграции и boilerplate из методички, то есть самого себя.

Файлы, доступные фрагментом, сюда попадают — в отличие от стилометрии.
Находка judge — это утверждение о конкретном фрагменте, который у нас на
руках, и его можно сверить; вывод об отсутствии чего-либо модель здесь и не
делает. Но фрагмент помечен в промпте, чтобы модель не рассуждала о работе
целиком по куску файла.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from pydantic import BaseModel, Field

from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.llm import (
    DataClass,
    Identity,
    LLMError,
    LLMUnavailable,
    PrivacyGateway,
    StructuredError,
    TaskKind,
    complete_json,
)

from ..schema import SignalKind, SignalResult, SignalStatus, Span

log = logging.getLogger(__name__)

MAX_CHARS_PER_ARTIFACT = 12_000

# Файлы, где генерация ожидаема и ничего не говорит о студенте.
TEMPLATE_PATTERNS = [
    re.compile(r"go\.(sum|mod)$"),
    re.compile(r".*\.pb\.go$"),
    re.compile(r"_pb2\.py$"),
    re.compile(r"(^|/)migrations?/"),
    re.compile(r"package-lock\.json$|yarn\.lock$|poetry\.lock$"),
    re.compile(r"(^|/)vendor/"),
    re.compile(r"Dockerfile$|docker-compose\.ya?ml$"),
    re.compile(r"\.gitignore$|\.env\.example$"),
]


def is_template(path: str) -> bool:
    return any(pattern.search(path) for pattern in TEMPLATE_PATTERNS)


SYSTEM = """Ты анализируешь студенческую работу на признаки того, что фрагменты \
написаны генеративной моделью, а не человеком.

Правила:

1. Указывай только те фрагменты, по которым можешь привести дословную цитату \
из работы. Без цитаты вывод не принимается.
2. Не оценивай качество работы. Плохой код — не признак генерации, отличный \
код — тоже.
3. Не считай признаком генерации шаблонный или общепринятый код: конфигурации, \
стандартные обработчики, типовые структуры проекта.
4. Опирайся на наблюдаемое: неестественная ровность изложения, избыточная \
пояснительность там, где её не просили, комментарии, объясняющие очевидное, \
клишированные обороты, несогласованность стиля между частями работы.
5. Если явных признаков нет — верни пустой список. Пустой ответ ценнее \
выдуманного.

Отвечай строго валидным JSON без markdown-обрамления."""

SCHEMA_HINT = """Схема ответа:

{
  "findings": [
    {
      "artifact": "путь к файлу",
      "quote": "дословный фрагмент из работы, не меньше 40 символов",
      "score": 0.0-1.0,
      "reason": "что именно указывает на генерацию, одно предложение"
    }
  ]
}"""


class JudgeFinding(BaseModel):
    artifact: str
    quote: str = ""
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


class JudgeResponse(BaseModel):
    findings: list[JudgeFinding] = Field(default_factory=list)


def analyse(
    gateway: PrivacyGateway,
    texts: list[ArtifactText],
    *,
    weight: float = 0.25,
    max_artifacts: int = 8,
    identities: Sequence[Identity] = (),
) -> SignalResult:
    result = SignalResult(kind=SignalKind.JUDGE, weight=weight)

    candidates = [a for a in texts if not is_template(a.path) and a.text.strip()]
    skipped = [a.path for a in texts if is_template(a.path)]
    if skipped:
        result.note = "исключены как шаблонные: " + ", ".join(skipped[:6])

    if not candidates:
        result.status = SignalStatus.UNAVAILABLE
        result.note = "нечего анализировать: остались только шаблонные файлы"
        return result

    candidates = sorted(candidates, key=lambda a: -len(a.text))[:max_artifacts]
    by_path = {a.path: a for a in candidates}

    try:
        response, _ = complete_json(
            gateway,
            _messages(candidates),
            JudgeResponse,
            task=TaskKind.JUDGE,
            data_class=DataClass.CONTAINS_PD,
            temperature=0.0,
            max_tokens=2000,
            identities=identities,
        )
    except (StructuredError, LLMError, LLMUnavailable) as exc:
        # Детектор не должен ронять обработку сдачи: три остальных сигнала
        # работают, а ревьюер увидит, что этот недоступен.
        log.warning("LLM-judge недоступен: %s", exc)
        result.status = SignalStatus.FAILED
        result.note = f"классификация моделью не выполнена: {exc}"
        return result

    scores: list[float] = []
    for finding in response.findings:
        artifact = by_path.get(finding.artifact) or _match_by_name(by_path, finding.artifact)
        if artifact is None:
            log.debug("judge сослался на неизвестный файл: %s", finding.artifact)
            continue

        span = _locate(artifact, finding)
        if span is None:
            # Цитата не подтвердилась — вывод отбрасывается вместе с находкой.
            log.debug("judge привёл цитату, которой нет в %s", finding.artifact)
            continue

        scores.append(finding.score)
        result.spans.append(span)
        result.findings.append(f"{artifact.path}: {finding.reason}")

    result.score = max(scores) if scores else 0.05
    if not scores:
        result.findings.append("Модель не нашла подтверждённых признаков генерации.")
    return result


# --------------------------------------------------------------------------- #

def _messages(artifacts: list[ArtifactText]) -> list[dict[str, str]]:
    blocks = []
    for artifact in artifacts:
        text = artifact.text[:MAX_CHARS_PER_ARTIFACT]
        suffix = "\n… фрагмент обрезан" if len(artifact.text) > MAX_CHARS_PER_ARTIFACT else ""
        header = f"### {artifact.path}"
        if artifact.partial:
            header += (
                "  — ФРАГМЕНТ: файл доступен не целиком, суди только о показанном тексте"
            )
        blocks.append(f"{header}\n{text}{suffix}")

    body = (
        "Проанализируй работу студента.\n\n"
        "<работа>\n" + "\n\n".join(blocks) + "\n</работа>\n\n" + SCHEMA_HINT
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": body},
    ]


def _match_by_name(by_path: dict[str, ArtifactText], path: str) -> ArtifactText | None:
    name = path.strip().split("/")[-1].lower()
    for known, artifact in by_path.items():
        if known.split("/")[-1].lower() == name:
            return artifact
    return None


def _locate(artifact: ArtifactText, finding: JudgeFinding) -> Span | None:
    """Найти цитату в тексте и превратить её в спан со смещениями.

    Сверка нестрогая по пробелам — по той же причине, что и в ревью: модель
    переносит строки иначе, чем файл. Но текст должен найтись: если его нет,
    находка не показывается вовсе.
    """
    quote = finding.quote.strip()
    if len(quote) < 40:
        return None

    text = artifact.text
    start = text.find(quote)
    if start == -1:
        start = _fuzzy_find(text, quote)
    if start is None or start == -1:
        return None

    end = start + len(quote)
    # Позиция в доступном тексте — не позиция в файле: у фрагмента нумерация
    # идёт с пропусками, поэтому строки берём из карты номеров артефакта.
    return Span(
        artifact=artifact.path,
        start=None if artifact.partial else start,
        end=None if artifact.partial else end,
        start_line=_head_line(artifact, text, start),
        end_line=_head_line(artifact, text, end),
        score=finding.score,
        signals=[SignalKind.JUDGE],
        reason=finding.reason,
        excerpt=quote[:200],
    )


def _head_line(artifact: ArtifactText, text: str, offset: int) -> int | None:
    index = text.count("\n", 0, offset)
    if index >= len(artifact.line_numbers):
        index = len(artifact.line_numbers) - 1
    return artifact.line_numbers[index] if index >= 0 else None


def _fuzzy_find(text: str, quote: str) -> int | None:
    """Поиск по тексту без учёта пробелов, с возвратом смещения в оригинале."""
    squeeze = lambda s: re.sub(r"\s+", "", s).lower()  # noqa: E731

    compact_quote = squeeze(quote)
    if not compact_quote:
        return None

    # Карта: позиция в сжатом тексте -> позиция в оригинале.
    positions: list[int] = []
    compact_chars: list[str] = []
    for index, char in enumerate(text):
        if not char.isspace():
            compact_chars.append(char.lower())
            positions.append(index)

    found = "".join(compact_chars).find(compact_quote)
    if found == -1:
        return None
    return positions[found]
