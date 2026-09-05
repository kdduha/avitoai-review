"""Форензика истории: коммиты git и ревизии документов.

Самый весомый сигнал ансамбля, и единственный полностью детерминированный.
Он ничего не знает о том, как выглядит текст модели, — он смотрит на то, как
работа появлялась во времени. Признаки почти не возникают случайно и
объясняются ревьюеру человеческим языком, а объяснимость здесь важнее
точности: по условиям курсов сигнал рекомендательный, и ревьюер должен видеть
основания, а не число.

Что ищем:

* **Взрывная вставка** — 640 строк одним коммитом за три минуты при среднем
  коммите в работе на 40 строк. Так пишут не с нуля, а вставляя.
* **Единственный коммит** на всю работу — истории разработки не было.
* **Неправдоподобный темп** — сотни строк в минуту.
* **Механические интервалы** — коммиты через равные промежутки, как будто
  раскладывали готовое, а не писали.
* **Пустая история** — сигнал не работает, и об этом надо сказать честно,
  а не выдать нулевой скор за отсутствие признаков.

**Чего мы не знаем.** `Revision` не несёт списка затронутых файлов: GitHub
отдаёт их отдельным запросом на каждый коммит, и ingest его не делает. Значит
сказать «вот эти строки появились в том самом коммите» нельзя. Придумывать
привязку хуже, чем её не иметь, поэтому спаны строятся от артефактов —
подсвечиваются крупные файлы, добавленные этой сдачей, — а в обосновании
прямо написано, что связь косвенная. Ревьюер должен понимать, что ему
показывают файл-кандидат, а не найденную сгенерированную строку.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from itertools import pairwise

from avito_reviewer.ingest import (
    Artifact,
    ArtifactRole,
    ChangeStatus,
    Revision,
    SubmissionBundle,
)

from ..schema import SignalKind, SignalResult, SignalStatus, Span

BULK_LINES = 250              # добавление крупнее — уже подозрительно
BULK_MINUTES = 5              # ...если уложилось в такой срок
FAST_LINES_PER_MINUTE = 80    # человеческий темп заметно ниже
MIN_EVENTS_FOR_RHYTHM = 5
RHYTHM_MAX_MEAN_MINUTES = 20  # ритм подозрителен только на коротких промежутках
MAX_SPANS = 8
MIN_SPAN_BYTES = 1_000        # мелкий файл ничего не объясняет про взрывную вставку

_INDIRECT = (
    "связь с коммитом косвенная: история не хранит списка файлов, "
    "подсвечен крупный файл, добавленный этой сдачей"
)


def analyse(bundle: SubmissionBundle, weight: float = 0.35) -> SignalResult:
    revisions = list(bundle.revisions)
    result = SignalResult(kind=SignalKind.FORENSICS, weight=weight)

    if not revisions:
        result.status = SignalStatus.UNAVAILABLE
        result.note = (
            "История изменений недоступна: сдача пришла снимком без git-истории. "
            "Самый весомый сигнал не участвует, вес перераспределён."
        )
        return result

    if len(revisions) == 1:
        result.score = 0.8
        result.findings.append(
            f"Вся работа состоит из одного коммита ({revisions[0].added_lines} "
            f"добавленных строк) — истории разработки нет."
        )
        result.spans = _candidate_spans(
            bundle, 0.8, "работа добавлена одним коммитом"
        )
        return result

    sizes = [r.added_lines for r in revisions if r.added_lines]
    median_size = statistics.median(sizes) if sizes else 0.0
    scores: list[float] = []
    reasons: list[str] = []

    # 1. Взрывные вставки на фоне остальной работы.
    for index, revision in enumerate(revisions):
        if revision.added_lines < BULK_LINES:
            continue
        minutes = _minutes_since_previous(revisions, index)
        rate = revision.added_lines / minutes if minutes else float("inf")

        bulk = minutes is not None and minutes <= BULK_MINUTES
        outlier = bool(median_size) and revision.added_lines > median_size * 8

        if bulk or outlier or rate > FAST_LINES_PER_MINUTE:
            score = 0.75 if (bulk and outlier) else 0.6
            scores.append(score)
            detail = f"{revision.added_lines} строк одним коммитом"
            if minutes is not None:
                detail += f" за {minutes:.0f} мин"
            if median_size:
                detail += f"; медиана коммита в работе — {median_size:.0f} строк"
            result.findings.append(detail)
            reasons.append(detail)

    # 2. Механический ритм: одинаковые промежутки между коммитами.
    #
    # Только для коротких промежутков. Студент, который коммитит каждый вечер
    # примерно в одно время, — это распорядок дня, а не подозрительно;
    # коммиты через равные полторы минуты — это выкладывание готового.
    gaps = _gaps_minutes(revisions)
    if len(gaps) >= MIN_EVENTS_FOR_RHYTHM - 1:
        mean_gap = statistics.mean(gaps)
        if 0 < mean_gap <= RHYTHM_MAX_MEAN_MINUTES:
            spread = statistics.pstdev(gaps) / mean_gap
            if spread < 0.15:
                scores.append(0.5)
                result.findings.append(
                    f"Коммиты идут почти через равные промежутки "
                    f"(разброс {spread:.0%} при среднем {mean_gap:.0f} мин) — "
                    f"похоже на выкладывание готового, а не на разработку."
                )

    # 3. Вся работа уложилась в один короткий заход.
    total_span = _minutes_between(revisions[0], revisions[-1])
    total_added = sum(r.added_lines for r in revisions)
    if total_span is not None and total_span < 30 and total_added > 400:
        scores.append(0.65)
        detail = f"{total_added} строк за {total_span:.0f} мин от первого до последнего коммита."
        result.findings.append(detail)
        reasons.append(detail)

    result.score = max(scores) if scores else 0.05
    if scores and reasons:
        result.spans = _candidate_spans(bundle, max(scores), "; ".join(reasons[:2]))
    if not scores:
        result.findings.append(
            f"История выглядит естественно: {len(revisions)} коммитов, "
            f"медиана {median_size:.0f} строк."
        )
    return result


# --------------------------------------------------------------------------- #

def _candidate_spans(bundle: SubmissionBundle, score: float, reason: str) -> list[Span]:
    """Файлы, на которые указывает подозрительная история — без обещания точности.

    Спан на весь файл, а не на строки: сигнал говорит «этот файл появился
    целиком за раз», и притворяться, что мы нашли конкретную строку, нельзя.
    """
    candidates = [
        artifact
        for artifact in bundle.artifacts
        if artifact.role is ArtifactRole.SOLUTION
        and artifact.status is ChangeStatus.ADDED
        and not artifact.is_binary
        and artifact.size_bytes >= MIN_SPAN_BYTES
    ]
    candidates.sort(key=_span_weight, reverse=True)
    return [
        Span(
            artifact=artifact.path,
            score=score,
            signals=[SignalKind.FORENSICS],
            reason=f"{reason} ({_INDIRECT})",
        )
        for artifact in candidates[:MAX_SPANS]
    ]


def _span_weight(artifact: Artifact) -> int:
    return artifact.size_bytes


def _minutes_since_previous(revisions: list[Revision], index: int) -> float | None:
    if index == 0:
        return None
    try:
        delta = revisions[index].authored_at - revisions[index - 1].authored_at
    except (AttributeError, TypeError):
        return None
    return max(delta.total_seconds() / 60, 0.0)


def _minutes_between(first: Revision, last: Revision) -> float | None:
    try:
        return (last.authored_at - first.authored_at).total_seconds() / 60
    except (AttributeError, TypeError):
        return None


def _gaps_minutes(revisions: list[Revision]) -> list[float]:
    gaps: list[float] = []
    for previous, current in pairwise(revisions):
        try:
            delta = current.authored_at - previous.authored_at
        except (AttributeError, TypeError):
            continue
        if timedelta(0) < delta < timedelta(days=1):
            gaps.append(delta.total_seconds() / 60)
    return gaps
