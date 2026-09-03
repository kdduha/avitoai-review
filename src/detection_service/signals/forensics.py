"""Форензика истории: коммиты git и ревизии документов.

Самый весомый сигнал ансамбля, и единственный полностью детерминированный.
Он ничего не знает о том, как выглядит текст модели, — он смотрит на то, как
работа появлялась во времени. Признаки почти не возникают случайно и
объясняются ревьюеру человеческим языком, а объяснимость здесь важнее
точности: по условиям курсов сигнал рекомендательный, и ревьюер должен видеть
основания, а не число.

Что ищем:

* **Взрывная вставка** — файл на 640 строк одним коммитом за три минуты при
  среднем коммите в работе на 40 строк. Так пишут не с нуля, а вставляя.
* **Единственный коммит** на всю работу — истории разработки не было.
* **Неправдоподобный темп** — сотни строк в минуту.
* **Механические интервалы** — коммиты через равные промежутки, как будто
  раскладывали готовое, а не писали.
* **Пустая история** — сигнал не работает, и об этом надо сказать честно,
  а не выдать нулевой скор за отсутствие признаков.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Any

from ..schema import SignalKind, SignalResult, SignalStatus, Span

BULK_LINES = 250              # добавление крупнее — уже подозрительно
BULK_MINUTES = 5              # ...если уложилось в такой срок
FAST_LINES_PER_MINUTE = 80    # человеческий темп заметно ниже
MIN_EVENTS_FOR_RHYTHM = 5
RHYTHM_MAX_MEAN_MINUTES = 20  # ритм подозрителен только на коротких промежутках


def analyse(bundle: Any, weight: float = 0.35) -> SignalResult:
    history = list(getattr(bundle, "history", []) or [])
    result = SignalResult(kind=SignalKind.FORENSICS, weight=weight)

    if not history:
        result.status = SignalStatus.UNAVAILABLE
        result.note = (
            "История изменений недоступна: сдача пришла снимком без git-истории. "
            "Самый весомый сигнал не участвует, вес перераспределён."
        )
        return result

    if len(history) == 1:
        event = history[0]
        result.score = 0.8
        result.findings.append(
            f"Вся работа состоит из одного коммита ({event.added} добавленных строк) — "
            f"истории разработки нет."
        )
        result.spans = _spans_for(event, 0.8, "работа добавлена одним коммитом")
        return result

    sizes = [e.added for e in history if e.added]
    median_size = statistics.median(sizes) if sizes else 0.0
    scores: list[float] = []

    # 1. Взрывные вставки на фоне остальной работы.
    for index, event in enumerate(history):
        if event.added < BULK_LINES:
            continue
        minutes = _minutes_since_previous(history, index)
        rate = event.added / minutes if minutes else float("inf")

        bulk = minutes is not None and minutes <= BULK_MINUTES
        outlier = median_size and event.added > median_size * 8

        if bulk or outlier or rate > FAST_LINES_PER_MINUTE:
            score = 0.75 if (bulk and outlier) else 0.6
            scores.append(score)
            detail = f"{event.added} строк одним коммитом"
            if minutes is not None:
                detail += f" за {minutes:.0f} мин"
            if median_size:
                detail += f"; медиана коммита в работе — {median_size:.0f} строк"
            result.findings.append(detail)
            result.spans.extend(_spans_for(event, score, detail))

    # 2. Механический ритм: одинаковые промежутки между коммитами.
    #
    # Только для коротких промежутков. Студент, который коммитит каждый вечер
    # примерно в одно время, — это распорядок дня, а не подозрительно;
    # коммиты через равные полторы минуты — это выкладывание готового.
    gaps = _gaps_minutes(history)
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
    total_span = _minutes_between(history[0], history[-1])
    total_added = sum(e.added for e in history)
    if total_span is not None and total_span < 30 and total_added > 400:
        scores.append(0.65)
        result.findings.append(
            f"{total_added} строк за {total_span:.0f} мин от первого до последнего коммита."
        )

    result.score = max(scores) if scores else 0.05
    if not scores:
        result.findings.append(
            f"История выглядит естественно: {len(history)} коммитов, "
            f"медиана {median_size:.0f} строк."
        )
    return result


# --------------------------------------------------------------------------- #

def _minutes_since_previous(history: list[Any], index: int) -> float | None:
    if index == 0:
        return None
    delta = history[index].at - history[index - 1].at
    return max(delta.total_seconds() / 60, 0.0)


def _minutes_between(first: Any, last: Any) -> float | None:
    try:
        return (last.at - first.at).total_seconds() / 60
    except (AttributeError, TypeError):
        return None


def _gaps_minutes(history: list[Any]) -> list[float]:
    gaps: list[float] = []
    for previous, current in zip(history, history[1:]):
        delta = current.at - previous.at
        if timedelta(0) < delta < timedelta(days=1):
            gaps.append(delta.total_seconds() / 60)
    return gaps


def _spans_for(event: Any, score: float, reason: str) -> list[Span]:
    """Спаны на уровне файлов, затронутых подозрительным коммитом.

    Точнее не получится и не нужно: сигнал говорит «этот файл появился
    целиком за раз», а не «вот эта строка сгенерирована».
    """
    paths = list(getattr(event, "touched_paths", []) or [])[:12]
    return [
        Span(
            artifact=path,
            score=score,
            signals=[SignalKind.FORENSICS],
            reason=reason,
        )
        for path in paths
    ]
