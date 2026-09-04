"""AI-слой: ревью-агент, детектор ГенИИ и единственный выход к моделям.

Всё, что здесь есть, работает только с `SubmissionBundle` и рубрикой — про
источник сдачи слой не знает ничего, эта зависимость заперта в `ingest`.
Наружу к моделям ходит один `PrivacyGateway`; прямые вызовы провайдеров вне
`ai.llm` запрещены архитектурно и проверяются тестом.
"""

from .content import ArtifactText, ContentResolver, build_texts, solution_texts
from .detection import DetectionReport, DetectionService, SignalKind, SignalStatus, Span
from .llm import PrivacyGateway, fake_gateway, gateway_from_config
from .review import (
    CriterionVerdict,
    Evidence,
    EvidenceStatus,
    ReviewDraft,
    ReviewService,
    explain,
)
from .rubric import Criterion, Rubric, RubricStore, load_rubric
from .service import AIService

__all__ = [
    "AIService",
    "ArtifactText",
    "ContentResolver",
    "Criterion",
    "CriterionVerdict",
    "DetectionReport",
    "DetectionService",
    "Evidence",
    "EvidenceStatus",
    "PrivacyGateway",
    "ReviewDraft",
    "ReviewService",
    "Rubric",
    "RubricStore",
    "SignalKind",
    "SignalStatus",
    "Span",
    "build_texts",
    "explain",
    "fake_gateway",
    "gateway_from_config",
    "load_rubric",
    "solution_texts",
]
