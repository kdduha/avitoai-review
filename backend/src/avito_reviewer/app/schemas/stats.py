"""Статистика по заданиям и потокам — из базы, а не из генератора.

Одно правило определяет, что здесь есть, а чего нет: **считается только то,
что действительно записано**. Утверждённых работ нет — среднего балла нет, и
на его месте `None`, а не ноль. Ноль читается как «все написали на ноль», и
это худшее, что можно показать руководителю рядом с настоящими числами.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScoreBucket(BaseModel):
    """Столбец гистограммы: доля максимума от `lo` до `hi`."""

    lo: float
    hi: float
    count: int


class AssignmentStats(BaseModel):
    id: UUID
    rubric_key: str
    title: str
    course_key: str
    stream_key: str
    deadline_at: datetime | None
    max_score: float

    submissions: int = 0
    awaiting: int = 0
    """Сдано, но ревьюер ещё не утвердил."""
    approved: int = 0
    late: int = 0
    """Сдано после срока. Считается по фактам, а не по штрафу: штраф зависит
    от `late_policy` рубрики, а просрочка — это просто дата."""

    average_score: float | None = None
    """Среднее по утверждённым. `None` — утверждённых нет."""
    pass_rate: float | None = None
    """Доля зачётов среди утверждённых. `None` по той же причине."""
    needs_attention: int = 0
    """Черновики, которые сама модель пометила как требующие человека."""

    histogram: list[ScoreBucket] = Field(default_factory=list)


class ReviewerLoadRow(BaseModel):
    username: str
    display_name: str
    assigned: int = 0
    approved: int = 0
    awaiting: int = 0


class StreamStats(BaseModel):
    id: UUID
    course_key: str
    stream_key: str
    title: str

    students: int = 0
    reviewers: int = 0
    assignments: int = 0

    submissions: int = 0
    awaiting: int = 0
    approved: int = 0
    unassigned: int = 0
    """Сдачи без ревьюера: их некому проверять, пока не распределили."""
    overdue: int = 0
    """Срок вышел, а оценка не утверждена."""

    average_score: float | None = None
    pass_rate: float | None = None

    by_assignment: list[AssignmentStats] = Field(default_factory=list)
    by_reviewer: list[ReviewerLoadRow] = Field(default_factory=list)


class StreamReviewerRow(BaseModel):
    username: str
    display_name: str
    role: str
    roster_id: str | None = None
    """Карточка из `backend/reviewers/`, если нашлась по логину или почте.

    Каталог ведут файлами, аккаунты живут в базе, и связаны они только именем.
    Нет карточки — распределение возьмёт ёмкость по умолчанию и скажет об этом.
    """
    capacity_minutes: int = 0
    skills: list[str] = Field(default_factory=list)


class AssignReviewersRequest(BaseModel):
    usernames: list[str] = Field(min_length=1)


class DistributeResult(BaseModel):
    """Что изменилось в базе, а не что посчитал солвер."""

    assigned: int
    unassigned: int
    reasons: list[str] = Field(default_factory=list)
    """Почему работа осталась без ревьюера — словами солвера, без пересказа."""
