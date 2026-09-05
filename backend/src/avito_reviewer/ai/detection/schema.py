"""Контракт детектора признаков ГенИИ.

Ограничение из условий курсов записано прямо: сигнал носит рекомендательный
характер, не является доказательством и не может автоматически влиять на
оценку. Схема сделана так, чтобы это было невозможно нарушить по забывчивости:
здесь нет ни одного поля, которое можно подставить в подсчёт балла, зато есть
доверительный интервал, основания и явный список ограничений проверки.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field, computed_field


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


def _span_id(artifact: str, start: int | None, end: int | None) -> str:
    """Устойчивый идентификатор спана: ревьюер подтверждает или отклоняет именно его."""
    key = f"{artifact}:{start or 0}-{end or 0}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


class Span(BaseModel):
    """Подозрительный фрагмент.

    Номера строк — в координатах полной версии файла, той же, что у цитат
    ревью: клик по спану в правой панели подсвечивает те же строки в левой.
    Смещения в символах есть только у файлов, доступных целиком — в тексте,
    собранном из диффа, они указывали бы в наш кусок, а не в файл.
    """

    artifact: str
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        return _span_id(self.artifact, self.start_line, self.end_line)

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

    tokens_in: int = 0
    tokens_out: int = 0
    cost_rub: float = 0.0

    advisory: bool = True
    """Вердикт рекомендательный: на балл он не влияет, решение принимает ревьюер.

    Флаг, а не фраза. Прозой это было `advisory_note` — дисклеймер, который
    печатался под каждым отчётом дословно и превращался в шум ровно там, где
    должен был предостерегать. Правило живёт в интерфейсе и в регламенте,
    а API отдаёт его машиночитаемо.
    """

    @classmethod
    def unavailable(cls, reason: str) -> DetectionReport:
        """Отчёт, который честно говорит, что проверки не было.

        Пустой отчёт и отсутствие отчёта — разные события: первое ревьюер
        должен увидеть с причиной, второе значит «не просили».
        """
        return cls(limitations=[reason])

    def signal(self, kind: SignalKind) -> SignalResult | None:
        return next((s for s in self.signals if s.kind is kind), None)

    @property
    def available_signals(self) -> list[SignalResult]:
        return [s for s in self.signals if s.contributes]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mismatch(self) -> bool:
        """Сигнал есть, а декларации нет — главный случай для ревьюера.

        По условию курса запрещено не использование ИИ, а несогласованное
        использование: «Если вы использовали ИИ — укажите это в работе».
        Поэтому интересно не «сгенерировано или нет», а расхождение между
        заявленным и найденным.
        """
        return self.overall_score >= 0.5 and self.declared_ai_usage is False
