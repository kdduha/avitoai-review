"""Контракт детектора признаков ГенИИ.

Ограничение из условий курсов записано прямо: сигнал носит рекомендательный
характер, не является доказательством и не может автоматически влиять на
оценку. Схема сделана так, чтобы это было невозможно нарушить по забывчивости:
здесь нет ни одного поля, которое можно подставить в подсчёт балла, зато есть
доверительный интервал, основания и явный список ограничений проверки.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SignalKind(str, Enum):
    FORENSICS = "forensics"      # история коммитов и ревизий
    PERPLEXITY = "perplexity"    # логпробы локальной модели
    STYLOMETRY = "stylometry"    # эвристики по коду и тексту
    JUDGE = "judge"              # классификация моделью


class SignalStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"  # нет данных или не настроен провайдер
    FAILED = "failed"


class ReviewerVerdict(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Span(BaseModel):
    """Подозрительный фрагмент.

    Смещения — в системе координат нормализованного текста артефакта, той же,
    что у цитат ревью. Клик по спану в правой панели подсвечивает те же
    строки в левой.
    """

    artifact: str
    artifact_id: str | None = None
    start: int | None = None
    end: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    score: float = Field(ge=0.0, le=1.0)
    signals: list[SignalKind] = Field(default_factory=list)
    reason: str = ""
    excerpt: str = ""
    ai_sensitive: bool = False
    reviewer_verdict: ReviewerVerdict = ReviewerVerdict.PENDING

    def human(self) -> str:
        if self.start_line:
            tail = f":{self.start_line}" + (f"–{self.end_line}" if self.end_line else "")
            return f"{self.artifact}{tail}"
        return self.artifact


class SignalResult(BaseModel):
    kind: SignalKind
    status: SignalStatus = SignalStatus.OK
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    weight: float = 0.0
    spans: list[Span] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    note: str = ""

    @property
    def contributes(self) -> bool:
        return self.status is SignalStatus.OK


class DetectionReport(BaseModel):
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    label: str = "недостаточно данных"

    signals: list[SignalResult] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    declared_ai_usage: bool | None = None
    declaration_note: str = ""

    advisory: bool = True
    advisory_note: str = (
        "Сигнал носит рекомендательный характер, не является доказательством "
        "нарушения и не влияет на балл автоматически. Решение принимает ревьюер."
    )

    def signal(self, kind: SignalKind) -> SignalResult | None:
        return next((s for s in self.signals if s.kind is kind), None)

    @property
    def available_signals(self) -> list[SignalResult]:
        return [s for s in self.signals if s.contributes]

    @property
    def mismatch(self) -> bool:
        """Сигнал есть, а декларации нет — главный случай для ревьюера.

        По условию курса запрещено не использование ИИ, а несогласованное
        использование: «Если вы использовали ИИ — укажите это в работе».
        Поэтому интересно не «сгенерировано или нет», а расхождение между
        заявленным и найденным.
        """
        return self.overall_score >= 0.5 and self.declared_ai_usage is False
