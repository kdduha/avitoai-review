"""Стилометрия: эвристики по коду и тексту.

Слабейший из четырёх сигналов и самый склонный к ложным срабатываниям —
аккуратный студент выглядит для него так же, как модель. Поэтому вес
небольшой, а каждое срабатывание обязано нести объяснение: ревьюеру нужно
понимать, что именно показалось подозрительным, чтобы отклонить сигнал
одним взглядом.

Для текста работает прокси-мера burstiness: у человека длина предложений
скачет, у сгенерированного текста она подозрительно ровная. Настоящая
перплексия делает это лучше, но требует локальной модели с logprobs —
здесь та же идея без модели вовсе.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from ..schema import SignalKind, SignalResult, SignalStatus, Span

# Обороты, которыми русскоязычные модели выдают себя чаще всего.
CLICHES = [
    "важно отметить", "стоит отметить", "стоит подчеркнуть", "необходимо отметить",
    "в современном мире", "играет важную роль", "в заключение", "таким образом",
    "не менее важным", "ключевым аспектом", "следует учитывать", "в первую очередь",
    "позволяет добиться", "комплексный подход", "рассмотрим подробнее",
]

CODE_SUFFIXES = (".go", ".py", ".js", ".ts", ".java", ".rs", ".c", ".cpp", ".kt")

MIN_TEXT_CHARS = 400   # на коротком фрагменте статистика не работает
MIN_CODE_LINES = 40


def analyse(artifacts: list[Any], weight: float = 0.15) -> SignalResult:
    result = SignalResult(kind=SignalKind.STYLOMETRY, weight=weight)
    scores: list[float] = []

    for artifact in artifacts:
        if artifact.path.lower().endswith(CODE_SUFFIXES):
            score, findings = _code_signals(artifact)
        else:
            score, findings = _text_signals(artifact)

        if score <= 0:
            continue

        scores.append(score)
        result.findings.extend(f"{artifact.path}: {f}" for f in findings)
        result.spans.append(
            Span(
                artifact=artifact.path,
                artifact_id=getattr(artifact, "id", None),
                score=score,
                signals=[SignalKind.STYLOMETRY],
                reason="; ".join(findings),
            )
        )

    if not scores:
        result.score = 0.05
        result.findings.append("Стилистических аномалий не обнаружено.")
        if not artifacts:
            result.status = SignalStatus.UNAVAILABLE
            result.note = "нет артефактов для анализа"
        return result

    # Берём не максимум, а взвешенное к максимуму среднее: один подозрительный
    # файл из двадцати — ещё не характеристика работы целиком.
    result.score = round(0.6 * max(scores) + 0.4 * statistics.mean(scores), 3)
    return result


# --------------------------------------------------------------------------- #

def _code_signals(artifact: Any) -> tuple[float, list[str]]:
    lines = artifact.text.splitlines()
    if len(lines) < MIN_CODE_LINES:
        return 0.0, []

    findings: list[str] = []
    score = 0.0

    code_lines = [ln for ln in lines if ln.strip()]
    comments = [ln for ln in code_lines if ln.strip().startswith(("//", "#", "/*", "*"))]
    density = len(comments) / len(code_lines) if code_lines else 0

    # Комментарий почти к каждой строке — характерная черта генерации.
    if density > 0.35:
        score = max(score, 0.55)
        findings.append(f"комментариями покрыто {density:.0%} строк")

    # Живой код обрастает следами работы: заметками, отладкой, мёртвыми кусками.
    has_todo = bool(re.search(r"\b(TODO|FIXME|XXX|HACK)\b", artifact.text))
    has_debug = bool(re.search(r"(fmt\.Print|console\.log|print\()", artifact.text))
    commented_code = sum(
        1 for ln in comments if re.search(r"[;{}()=]|:=", ln)
    )
    if not has_todo and not has_debug and not commented_code and len(code_lines) > 120:
        score = max(score, 0.4)
        findings.append("нет ни заметок, ни отладочных следов, ни закомментированного кода")

    # Одинаковые по длине функции — признак шаблонной генерации.
    blocks = _function_lengths(artifact.text)
    if len(blocks) >= 4:
        mean_len = statistics.mean(blocks)
        if mean_len > 0 and statistics.pstdev(blocks) / mean_len < 0.12:
            score = max(score, 0.45)
            findings.append(f"функции почти одинаковой длины (около {mean_len:.0f} строк)")

    return score, findings


def _text_signals(artifact: Any) -> tuple[float, list[str]]:
    text = artifact.text
    if len(text) < MIN_TEXT_CHARS:
        return 0.0, []

    findings: list[str] = []
    score = 0.0
    lowered = text.lower()

    hits = [phrase for phrase in CLICHES if phrase in lowered]
    if len(hits) >= 3:
        score = max(score, 0.5 + 0.05 * min(len(hits) - 3, 4))
        findings.append("характерные обороты: " + ", ".join(f"«{h}»" for h in hits[:4]))

    sentences = [s.strip() for s in re.split(r"[.!?]+\s", text) if len(s.strip()) > 20]
    if len(sentences) >= 8:
        lengths = [len(s) for s in sentences]
        mean_len = statistics.mean(lengths)
        burstiness = statistics.pstdev(lengths) / mean_len if mean_len else 1.0
        # У человека длина предложений скачет; ровность — признак генерации.
        if burstiness < 0.35:
            score = max(score, 0.45)
            findings.append(
                f"длина предложений подозрительно ровная (разброс {burstiness:.0%})"
            )

    return score, findings


def _function_lengths(text: str) -> list[int]:
    """Длины функций по строкам — грубо, но одинаково для Go и Python."""
    starts = [
        i for i, line in enumerate(text.splitlines())
        if re.match(r"\s*(func |def )", line)
    ]
    if len(starts) < 2:
        return []
    total = len(text.splitlines())
    return [b - a for a, b in zip(starts, starts[1:] + [total])]
