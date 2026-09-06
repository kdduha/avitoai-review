"""Сведение сигналов в один вердикт.

**Веса перенормируются по доступным сигналам.** Если истории коммитов нет — а в
выгрузках-снимках её нет, — самый весомый сигнал молчит. Нулевой вклад читался
бы как «признаков не найдено» там, где на самом деле «не смотрели»: веса делятся
между оставшимися, ограничение выписывается в отчёт явно.

**Доверительный интервал строится на разногласии.** Сигналы разной природы
говорят одно — интервал узкий; форензика кричит, а стилометрия молчит — широкий.

**Спаны объединяются по перекрытию.** Один фрагмент, найденный двумя сигналами,
— одна карточка с двумя основаниями, а не две подряд.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

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

    # Вес недоступного сигнала не уходит в пользу «чисто», а перераспределяется
    # между теми, кто смог посмотреть.
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
    # Вперёд — спаны на критериях, чувствительных к самостоятельности:
    # сгенерированный docker-compose и карта рисков это разные события.
    report.spans = sorted(spans, key=lambda s: (not s.ai_sensitive, -s.score))

    report.limitations.extend(_reliability_note(available))
    return report


def merge_spans(spans: Iterable[Span]) -> list[Span]:
    """Слить пересекающиеся спаны одного файла в один с общими основаниями.

    Пересечение считается по номерам строк, а не по смещениям в символах.
    Смещений нет у находок в файлах, доступных фрагментом, — но строки есть, и
    ронять их в «спан на весь файл» нельзя: ревьюер потеряет место находки, а
    интерфейс покажет карточку без диапазона.
    """
    by_artifact: dict[str, list[Span]] = {}
    for span in spans:
        by_artifact.setdefault(span.artifact, []).append(span)

    merged: list[Span] = []
    for artifact_spans in by_artifact.values():
        by_line = [s for s in artifact_spans if s.start_line is not None]
        by_char = [s for s in artifact_spans if s.start_line is None and s.start is not None]
        whole_file = [s for s in artifact_spans if s.start_line is None and s.start is None]

        merged.extend(_merge_run(by_line, _line_bounds))
        merged.extend(_merge_run(by_char, _char_bounds))

        # Спаны на весь файл (форензика, стилометрия): один на файл.
        if whole_file:
            fused = whole_file[0].model_copy(deep=True)
            for span in whole_file[1:]:
                fused = _fuse(fused, span)
            merged.append(fused)

    return merged


def _line_bounds(span: Span) -> tuple[int, int]:
    start = span.start_line or 0
    return start, span.end_line or start


def _char_bounds(span: Span) -> tuple[int, int]:
    start = span.start or 0
    return start, span.end or start


def _merge_run(
    spans: list[Span], bounds: Callable[[Span], tuple[int, int]]
) -> list[Span]:
    """Слить пересекающиеся спаны, сравнивая их в одной системе координат."""
    merged: list[Span] = []
    current: Span | None = None
    for span in sorted(spans, key=lambda s: bounds(s)[0]):
        if current is None:
            current = span.model_copy(deep=True)
            continue
        if bounds(span)[0] <= bounds(current)[1]:
            current = _fuse(current, span)
        else:
            merged.append(current)
            current = span.model_copy(deep=True)
    if current is not None:
        merged.append(current)
    return merged


def _fuse(left: Span, right: Span) -> Span:
    fused = left.model_copy(deep=True)
    fused.start = _min(left.start, right.start)
    fused.end = max(left.end or 0, right.end or 0) or None
    fused.start_line = _min(left.start_line, right.start_line)
    fused.end_line = max(left.end_line or 0, right.end_line or 0) or None
    fused.signals = list(dict.fromkeys(left.signals + right.signals))
    # Совпадение двух независимых сигналов усиливает вывод, но не до единицы:
    # это всё ещё указание, а не доказательство.
    fused.score = round(min(1.0, max(left.score, right.score) + 0.1 * (len(fused.signals) - 1)), 3)
    reasons = [r for r in (left.reason, right.reason) if r]
    fused.reason = "; ".join(dict.fromkeys(reasons))
    fused.excerpt = left.excerpt or right.excerpt
    return fused


def _min(left: int | None, right: int | None) -> int | None:
    present = [value for value in (left, right) if value is not None]
    return min(present) if present else None


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


def _reliability_note(available: list[SignalResult]) -> list[str]:
    """Ограничение этого прогона, а не постоянная методологическая сноска.

    Раньше сюда же попадали две фразы про минимальную длину фрагмента и про
    исключение шаблонного кода. Они повторялись дословно в каждом отчёте, а
    названный в них порог («короче 200 символов») не совпадал ни с одним
    порогом в коде: у перплексии MIN_CHARS = 800, у стилометрии
    MIN_TEXT_CHARS = 400 и MIN_CODE_LINES = 40. Постоянная сноска — тем более
    неверная — это документация, а не ограничение прогона.
    """
    if len(available) < 3:
        return [
            f"Вывод построен всего на {len(available)} сигнале(ах) из четырёх — "
            f"надёжность ниже обычной."
        ]
    return []
