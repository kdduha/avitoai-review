"""Детектор признаков генеративного ИИ.

Ансамбль из четырёх сигналов разной природы, половина веса — на
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
from .service import DetectionConfig, DetectionService

__all__ = [
    "DetectionConfig",
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
