"""AI-слой: ревью-агент, детектор ГенИИ и единственный выход к моделям.

Всё, что здесь есть, работает только с `SubmissionBundle` и рубрикой — про
источник сдачи слой не знает ничего, эта зависимость заперта в `ingest`.
Наружу к моделям ходит один `PrivacyGateway`; прямые вызовы провайдеров вне
`ai.llm` запрещены архитектурно и проверяются тестом.
"""

from .chat import AgentStep, ChatStep, ProposedPatch, run_chat
from .compiler import CompilerError, RubricCompiler, RubricDraft
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
    "AgentStep",
    "ArtifactText",
    "ChatStep",
    "CompilerError",
    "ContentResolver",
    "Criterion",
    "CriterionVerdict",
    "DetectionReport",
    "DetectionService",
    "Evidence",
    "EvidenceStatus",
    "PrivacyGateway",
    "ProposedPatch",
    "ReviewDraft",
    "ReviewService",
    "Rubric",
    "RubricCompiler",
    "RubricDraft",
    "RubricStore",
    "SignalKind",
    "SignalStatus",
    "Span",
    "build_texts",
    "explain",
    "fake_gateway",
    "gateway_from_config",
    "load_rubric",
    "run_chat",
    "solution_texts",
]
