from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from avito_reviewer.ai.compiler import RubricDraft
from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.detection import DetectionReport
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.rubric import Rubric
from avito_reviewer.ingest import ArtifactRole, SubmissionBundle, SubmissionSource


class SubmissionRequest(BaseModel):
    """Ссылка на сдачу плюс то, чего из неё не вывести."""

    link: str
    source: SubmissionSource = SubmissionSource.GITHUB_PR
    assignment_id: UUID | None = None
    deadline_at: datetime | None = None
    student_internal_id: str | None = None
    student_name: str | None = Field(
        default=None,
        description=(
            "ФИО студента, если платформа его знает. Не уходит в модель: шлюз "
            "вычищает его вместе с падежами и инициалами. В бандле имени нет "
            "намеренно, поэтому без этого поля оно остаётся на общих детекторах."
        ),
    )


class ReviewRequest(SubmissionRequest):
    """Запрос на черновик ревью.

    Рубрика приходит либо по идентификатору из каталога, либо целиком в теле —
    второе нужно, пока Rubric Compiler отдаёт её на подтверждение методисту и
    в каталоге её ещё нет.
    """

    rubric_id: str | None = None
    rubric: Rubric | None = None
    condition_text: str = ""
    gate_facts: list[str] = Field(
        default_factory=list,
        description="Факты Format Gate: проверены кодом, модель их не пересчитывает",
    )

    @model_validator(mode="after")
    def _one_rubric(self) -> ReviewRequest:
        if (self.rubric_id is None) == (self.rubric is None):
            raise ValueError("укажите ровно одно: rubric_id или rubric")
        return self


class DetectRequest(SubmissionRequest):
    rubric_id: str | None = None


class ArtifactTextOut(BaseModel):
    """Текст артефакта в том виде, в котором его видела модель.

    Ровно то, что нужно панели файлов: цитата с номерами строк подсвечивается
    в этом тексте и ни в чём другом. `partial` говорит ревьюеру, что файл
    показан не целиком — и что вывод «этого в работе нет» здесь ненадёжен.
    """

    path: str
    role: ArtifactRole
    lang: str | None
    partial: bool
    origin: str = Field(description="excerpt | fetched | diff — откуда взялся текст")
    first_line: int
    last_line: int
    line_numbers: list[int] = Field(
        description=(
            "Номер каждой строки `text` в полной версии файла. У фрагмента из "
            "диффа они идут с пропусками, поэтому нумеровать вьювером от "
            "`first_line` нельзя — цитата уедет на чужую строку."
        )
    )
    changed_lines: str = Field(description="строки этой сдачи, например «1–48, 120»")
    text: str

    @classmethod
    def of(cls, text: ArtifactText) -> ArtifactTextOut:
        return cls(
            path=text.path,
            role=text.role,
            lang=text.lang,
            partial=text.partial,
            origin=text.origin,
            first_line=text.line_numbers[0] if text.line_numbers else 0,
            last_line=text.line_numbers[-1] if text.line_numbers else 0,
            line_numbers=text.line_numbers,
            changed_lines=text.changed_summary(),
            text=text.text,
        )


class ReviewResponse(BaseModel):
    """Всё, что нужно рабочему месту ревьюера за один запрос.

    Сдача, тексты файлов и черновик приходят вместе намеренно: разложить это
    на три вызова значило бы три раза сходить в GitHub за одним и тем же.
    """

    bundle: SubmissionBundle
    files: list[ArtifactTextOut]
    draft: ReviewDraft


class DetectResponse(BaseModel):
    bundle: SubmissionBundle
    files: list[ArtifactTextOut]
    report: DetectionReport


class RubricSummary(BaseModel):
    assignment_id: str
    title: str
    course: str
    stage: str | None
    criteria: int
    total_max: float
    pass_threshold: float | None

    @classmethod
    def of(cls, rubric: Rubric) -> RubricSummary:
        return cls(
            assignment_id=rubric.assignment_id,
            title=rubric.title,
            course=rubric.course,
            stage=rubric.stage,
            criteria=len(rubric.criteria),
            total_max=rubric.scale.total_max,
            pass_threshold=rubric.scale.pass_threshold,
        )


class CostSummary(BaseModel):
    """Сводка обращений к моделям с момента старта — для карточки экономики прогона."""

    calls: int
    external_calls: int
    errors: int
    tokens_in: int
    tokens_out: int
    redactions: int
    cost_rub: float


class CompileRubricRequest(BaseModel):
    """Условие задания, из которого нужно собрать черновик рубрики."""

    assignment_id: str
    condition_text: str = Field(min_length=40, description="текст условия целиком")
    course: str = ""
    hint: str = Field(default="", description="пожелание методиста: шкала, акценты, что учесть")


class CompileRubricResponse(BaseModel):
    """Черновик рубрики. Не установлен и не сохранён — это предложение методисту.

    `grounded_share` — доля критериев, подтверждённых дословной цитатой из
    условия. Всё, что ниже единицы, требует прочтения человеком в первую
    очередь: там модель пересказала, а не процитировала.
    """

    draft: RubricDraft
    grounded_share: float


class ConfirmRubricRequest(BaseModel):
    """Подтверждение рубрики методистом: она вступает в силу для всего потока."""

    rubric: Rubric
    confirmed_by: str = Field(min_length=2, description="кто подтверждает — попадёт в рубрику")
    overwrite: bool = Field(
        default=False,
        description=(
            "Переписать существующую рубрику. По умолчанию нельзя: по ней могли "
            "быть проверены работы, и подмена задним числом делает их баллы "
            "необъяснимыми."
        ),
    )


class ConfirmRubricResponse(BaseModel):
    rubric: Rubric
    path: str
