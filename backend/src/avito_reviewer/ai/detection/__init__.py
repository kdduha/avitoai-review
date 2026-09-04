"""Детектор признаков генеративного ИИ.

Ансамбль из четырёх сигналов разной природы, треть веса — на
детерминированной форензике истории. Вывод рекомендательный: спаны с
основаниями и доверительный интервал, решение принимает ревьюер.
"""

from .ensemble import combine, merge_spans
from .schema import (
    DetectionReport,
    ReviewerVerdict,
    SignalKind,
    SignalResult,
    SignalStatus,
    Span,
)
from .service import DetectionService

__all__ = [
    "DetectionReport",
    "DetectionService",
    "ReviewerVerdict",
    "SignalKind",
    "SignalResult",
    "SignalStatus",
    "Span",
    "combine",
    "merge_spans",
]
