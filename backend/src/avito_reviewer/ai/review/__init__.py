"""Ревью-агент: разбор работы по критериям рубрики.

Модель оценивает отдельный критерий и обязана приложить цитату. Итоговый
балл считает `aggregate.py`, а не модель.
"""

from .aggregate import ScoreBreakdown, aggregate, explain
from .evidence import EvidenceValidator
from .prompts import batch_criteria, build_messages, render_artifact, render_work
from .schema import (
    CriterionBatch,
    CriterionVerdict,
    Evidence,
    EvidenceStatus,
    ReviewDraft,
)
from .service import ReviewService

__all__ = [
    "CriterionBatch",
    "CriterionVerdict",
    "Evidence",
    "EvidenceStatus",
    "EvidenceValidator",
    "ReviewDraft",
    "ReviewService",
    "ScoreBreakdown",
    "aggregate",
    "batch_criteria",
    "build_messages",
    "explain",
    "render_artifact",
    "render_work",
]
