"""Сведение сигналов в один вердикт.

Три решения, которые здесь важнее формул.

**Веса перенормируются по доступным сигналам.** Если истории коммитов нет —
а в выгрузках-снимках её нет, — самый весомый сигнал молчит. Считать при
этом, что его вклад равен нулю, значит выдать «признаков не найдено» там, где
на самом деле «не смотрели». Веса делятся между оставшимися, а ограничение
выписывается в отчёт явно.

**Доверительный интервал строится на разногласии.** Когда сигналы разной
природы говорят одно и то же, интервал узкий. Когда форензика кричит, а
стилометрия молчит, интервал широкий — и ревьюер видит, что уверенности нет.
Это честнее одного числа.

**Спаны объединяются по перекрытию.** Один и тот же фрагмент, найденный
двумя сигналами, — сильное указание, и в интерфейсе он должен быть одной
карточкой с двумя основаниями, а не двумя карточками подряд.
"""

from __future__ import annotations

from collections.abc import Iterable

from .schema import DetectionReport, SignalKind, SignalResult, Span

LABELS = [
    (0.75, "высокая вероятность"),
    (0.5, "средняя вероятность"),
    (0.25, "низкая вероятность"),
    (0.0, "признаков не найдено"),
]


def combine(
    signals: list[SignalResult],
    *,
    ai_sensitive_paths: set[str] | None = None,
) -> DetectionReport:
    report = DetectionReport(signals=list(signals))

    available = [s for s in signals if s.contributes]
    unavailable = [s for s in signals if not s.contributes]

    for signal in unavailable:
        report.limitations.append(
            f"Сигнал «{_name(signal.kind)}» не участвовал: {signal.note or 'нет данных'}"
        )

    if not available:
        report.overall_score = 0.0
        report.label = "недостаточно данных"
        report.confidence_low = report.confidence_high = 0.0
        report.limitations.append(
            "Ни один сигнал не отработал — вывод сделать не на чем."
        )
        return report

    # Перенормировка: вес недоступного сигнала не исчезает в пользу «чисто»,
    # а распределяется между теми, кто смог посмотреть.
    total_weight = sum(s.weight for s in available) or 1.0
    score = sum(s.score * s.weight for s in available) / total_weight
    report.overall_score = round(min(1.0, max(0.0, score)), 3)

    report.confidence_low, report.confidence_high = _interval(available, report.overall_score)
    report.label = _label(report.overall_score)

    spans = merge_spans(s for signal in available for s in signal.spans)
    if ai_sensitive_paths:
        for span in spans:
            if span.artifact in ai_sensitive_paths:
                span.ai_sensitive = True
    # Спаны на критериях, чувствительных к самостоятельности, — вперёд:
    # сгенерированный docker-compose и сгенерированная карта рисков это
    # разные события, и ревьюер должен увидеть второе первым.
    report.spans = sorted(spans, key=lambda s: (not s.ai_sensitive, -s.score))

    report.limitations.extend(_standard_limitations(available))
    return report


# --------------------------------------------------------------------------- #

def merge_spans(spans: Iterable[Span]) -> list[Span]:
    """Слить пересекающиеся спаны одного файла в один с общими основаниями."""
    by_artifact: dict[str, list[Span]] = {}
    for span in spans:
        by_artifact.setdefault(span.artifact, []).append(span)

    merged: list[Span] = []
    for artifact_spans in by_artifact.values():
        positioned = [s for s in artifact_spans if s.start is not None]
        whole_file = [s for s in artifact_spans if s.start is None]

        positioned.sort(key=lambda s: (s.start or 0))
        current: Span | None = None
        for span in positioned:
            if current is None:
                current = span.model_copy(deep=True)
                continue
            if span.start is not None and current.end is not None and span.start <= current.end:
                current = _fuse(current, span)
            else:
                merged.append(current)
                current = span.model_copy(deep=True)
        if current is not None:
            merged.append(current)

        # Файловые спаны от форензики: сливаем в один на файл.
        if whole_file:
            fused = whole_file[0].model_copy(deep=True)
            for span in whole_file[1:]:
                fused = _fuse(fused, span)
            merged.append(fused)

    return merged


def _fuse(left: Span, right: Span) -> Span:
    fused = left.model_copy(deep=True)
    fused.end = max(left.end or 0, right.end or 0) or None
    fused.end_line = max(left.end_line or 0, right.end_line or 0) or None
    fused.signals = list(dict.fromkeys(left.signals + right.signals))
    # Совпадение двух независимых сигналов усиливает вывод, но не до единицы:
    # это всё ещё указание, а не доказательство.
    fused.score = round(min(1.0, max(left.score, right.score) + 0.1 * (len(fused.signals) - 1)), 3)
    reasons = [r for r in (left.reason, right.reason) if r]
    fused.reason = "; ".join(dict.fromkeys(reasons))
    fused.excerpt = left.excerpt or right.excerpt
    return fused


def _interval(available: list[SignalResult], score: float) -> tuple[float, float]:
    """Ширина интервала растёт с разногласием сигналов и с их нехваткой."""
    values = [s.score for s in available]
    spread = (max(values) - min(values)) if len(values) > 1 else 0.5
    missing_penalty = 0.05 * (4 - len(available))
    half = min(0.35, spread / 2 + missing_penalty)
    return round(max(0.0, score - half), 3), round(min(1.0, score + half), 3)


def _label(score: float) -> str:
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return "признаков не найдено"


def _name(kind: SignalKind) -> str:
    return {
        SignalKind.FORENSICS: "форензика истории",
        SignalKind.PERPLEXITY: "перплексия",
        SignalKind.STYLOMETRY: "стилометрия",
        SignalKind.JUDGE: "классификация моделью",
    }[kind]


def _standard_limitations(available: list[SignalResult]) -> list[str]:
    limits = [
        "Фрагменты короче 200 символов не оцениваются: на них статистика не работает.",
        "Шаблонный и сгенерированный инструментами код исключён из анализа.",
    ]
    if len(available) < 3:
        limits.append(
            f"Вывод построен всего на {len(available)} сигнале(ах) из четырёх — "
            f"надёжность ниже обычной."
        )
    return limits
