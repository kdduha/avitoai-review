"""Что видит и делает студент: свои задания, своя сдача, свои оценки.

Одно правило определяет здесь всё: **студенту не показывают черновик**.
Пока ревьюер не утвердил разбор, работа для студента находится «на проверке»
и никакого балла у неё нет. Показать предварительный балл значило бы объявить
студенту оценку, которую поставила модель, — а её ставит человек, и он ещё не
поставил. Отсюда `score` только у утверждённых и отдельный `StudentVerdict`
без цитат, уверенностей и служебных пометок разбора.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from avito_reviewer.ingest import SubmissionSource


class StudentAssignment(BaseModel):
    """Задание, которое студенту предстоит сдать."""

    id: UUID
    course_key: str
    course_title: str = ""
    """Название курса словами. Студент учится на нескольких сразу, и `go` в
    качестве заголовка группы ему ничего не говорит."""
    stream_key: str
    stream_title: str = ""
    title: str
    description: str
    max_score: float
    criteria: int
    opens_at: datetime | None
    deadline_at: datetime | None

    submissions: int = 0
    """Сколько раз студент уже сдавал это задание."""
    best_score: float | None = None
    """Лучший из утверждённых баллов. `None` — утверждённых сдач ещё нет."""


class StudentSubmitRequest(BaseModel):
    assignment_id: UUID
    link: str = Field(min_length=1)
    source: SubmissionSource = SubmissionSource.GITHUB_PR


class StudentVerdict(BaseModel):
    """Разбор одного критерия в том виде, в котором его читает студент.

    Ни цитат, ни уверенности модели, ни отметок «нужен человек»: это кухня
    проверки, а не обратная связь. Остаётся балл, объяснение и что докрутить.
    """

    criterion_id: str
    title: str
    score: float
    max_score: float
    feedback: str
    """`student_feedback` вердикта; если он пуст — сам вердикт."""
    improvement_hint: str


class StudentReviewSummary(BaseModel):
    """Отзыв о работе целиком, словами.

    То, чего студенту не хватало больше всего: по критериям всё расписано, а
    связного слова о работе не было. Приезжает только у утверждённых работ —
    как и балл: пока ревьюер не подтвердил разбор, это ещё не отзыв, а
    заготовка.
    """

    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    encouragement: str = ""


class StudentSubmission(BaseModel):
    """Своя сдача глазами студента."""

    id: UUID
    assignment_title: str
    course_key: str
    stream_key: str
    origin_url: str
    submitted_at: datetime | None
    deadline_at: datetime | None
    created_at: datetime

    approved: bool
    """Утверждена ли оценка человеком. Пока нет — балла нет вовсе."""
    score: float | None = None
    max_score: float = 0.0
    passed: bool | None = None
    pass_explanation: str = ""
    late_explanation: str = ""
    summary: StudentReviewSummary | None = None
    verdicts: list[StudentVerdict] = Field(default_factory=list)
