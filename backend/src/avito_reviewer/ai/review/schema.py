"""Контракт вывода ревью-агента.

Одна и та же схема описывает то, что мы просим у модели, то, что проверяют
тесты, и то, что уходит в интерфейс ревьюера. Расхождение между этими тремя
местами — самый дешёвый способ получить систему, которая «вроде работает».
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field

from avito_reviewer.ai.gate import GateReport


class EvidenceStatus(str, Enum):
    VALID = "valid"                    # цитата найдена там, где указано
    WRONG_LOCATION = "wrong_location"  # файл есть, но текста в этих строках нет
    NOT_IN_AVAILABLE_PART = "not_in_available_part"
    """Файл доступен фрагментом, и в этом фрагменте цитаты нет.

    Отдельный статус, а не разновидность «не найдено»: мы не видели файла
    целиком, поэтому «цитата выдумана» здесь недоказуемо. Ревьюеру нужно
    различать «модель соврала» и «мы не смотрели».
    """
    NO_SUCH_ARTIFACT = "no_such_artifact"
    EMPTY = "empty"


class Evidence(BaseModel):
    """Цитата, на которую опирается вердикт.

    Модель обязана указать не только файл, но и строки, и сам текст: без
    текста нечего сверять, без строк нечего подсвечивать в интерфейсе.
    """

    artifact: str = Field(description="путь к файлу в сдаче")
    start_line: int | None = Field(default=None, description="номер первой строки")
    end_line: int | None = Field(default=None, description="номер последней строки")
    quote: str = Field(default="", description="дословный фрагмент из файла")

    # заполняется валидатором, модель этого не присылает
    status: EvidenceStatus = EvidenceStatus.EMPTY
    char_start: int | None = None
    char_end: int | None = None
    note: str = ""

    @property
    def is_valid(self) -> bool:
        return self.status is EvidenceStatus.VALID

    def human(self) -> str:
        if self.start_line and self.end_line and self.end_line != self.start_line:
            return f"{self.artifact}:{self.start_line}–{self.end_line}"
        if self.start_line:
            return f"{self.artifact}:{self.start_line}"
        return self.artifact


class CriterionVerdict(BaseModel):
    """Оценка одного критерия.

    Обратите внимание, чего здесь нет: итогового балла работы. Модель
    оценивает критерии по отдельности, а сумму считает агрегатор — арифметику
    ей не доверяем.
    """

    criterion_id: str
    score: float = Field(description="балл по этому критерию, не выше максимума")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verdict: str = Field(description="одно-два предложения: что именно сделано и что нет")
    evidence: list[Evidence] = Field(default_factory=list)
    student_feedback: str = Field(
        default="", description="формулировка для студента в поддерживающем тоне"
    )
    improvement_hint: str = Field(default="", description="что конкретно докрутить")
    needs_human_attention: bool = False
    attention_reason: str = ""

    @property
    def valid_evidence(self) -> list[Evidence]:
        return [e for e in self.evidence if e.is_valid]


class CriterionBatch(BaseModel):
    """Ответ модели на один запрос: несколько критериев за раз."""

    verdicts: list[CriterionVerdict]


class ReviewSummary(BaseModel):
    """Связное слово о работе целиком: что удалось, что нет, и что дальше.

    Отдельный шаг после того, как критерии уже оценены и цитаты сверены, —
    и это главное ограничение: резюме пересказывает **уже подтверждённые
    вердикты**, а не работу. Файлов ему не показывают вовсе, поэтому новых
    утверждений о коде оно физически сделать не может: соврать можно только
    про то, что видишь.

    Балл резюме не трогает: его считает агрегатор, а модель здесь пишет текст.
    """

    strengths: list[str] = Field(
        default_factory=list, description="что в работе сделано хорошо, по пунктам"
    )
    improvements: list[str] = Field(
        default_factory=list, description="что именно доработать, по пунктам"
    )
    encouragement: str = Field(
        default="",
        description="одно-два предложения студенту: по-человечески и без снисходительности",
    )

    @property
    def is_empty(self) -> bool:
        return not (self.strengths or self.improvements or self.encouragement)


class ReviewDraft(BaseModel):
    """Черновик, который увидит ревьюер."""

    assignment_id: str
    rubric_title: str = ""
    verdicts: list[CriterionVerdict] = Field(default_factory=list)

    raw_score: float = 0.0
    score: float = 0.0
    max_score: float = 0.0
    passed: bool | None = None
    """`None` — порога зачёта в рубрике нет, решает ревьюер."""
    pass_explanation: str = ""
    late_explanation: str = ""

    summary: ReviewSummary | None = None
    """Разбор словами. `None` — модель до него не дошла: работа не принята по
    формату, или шаг резюме не удался. Пустое место честнее выдуманного
    абзаца, поэтому заглушки здесь нет."""

    gate_facts: list[str] = Field(default_factory=list)
    gate: GateReport | None = None
    """Результат формальных проверок. `blocked` значит, что модель не запускалась."""
    needs_human_attention: bool = False
    attention_reasons: list[str] = Field(default_factory=list)

    partial_artifacts: list[str] = Field(default_factory=list)
    """Файлы, которые модель видела не целиком.

    Идёт в интерфейс: вердикт «этого в работе нет», относящийся к такому
    файлу, ревьюер обязан перепроверить сам.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    cost_rub: float = 0.0
    failed_criteria: list[str] = Field(default_factory=list)

    def verdict(self, criterion_id: str) -> CriterionVerdict | None:
        return next((v for v in self.verdicts if v.criterion_id == criterion_id), None)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_coverage(self) -> float:
        """Доля вердиктов, подкреплённых проверенной цитатой."""
        if not self.verdicts:
            return 0.0
        with_evidence = sum(1 for v in self.verdicts if v.valid_evidence)
        return round(with_evidence / len(self.verdicts), 2)
