"""Что сервисы ожидают от ядра.

Ядро (`reviewer-core`) разрабатывается параллельно другим человеком. Чтобы не
блокировать друг друга и не ловить рассинхрон на каждом его коммите, сервисы
не импортируют ядро, а описывают структурные протоколы: любой объект нужной
формы подойдёт. Модели ядра им удовлетворяют, а в тестах используются
лёгкие двойники.

Правило простое: если сервису понадобилось поле, которого здесь нет, — сначала
оно появляется тут, и только потом в коде сервиса.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LocatorLike(Protocol):
    start_line: int | None
    end_line: int | None
    page: int | None
    sheet: str | None
    cell_range: str | None
    notebook_cell: int | None


@runtime_checkable
class SegmentLike(Protocol):
    index: int
    start: int
    end: int
    locator: Any


@runtime_checkable
class ArtifactLike(Protocol):
    """Файл сдачи после нормализации."""

    id: str
    path: str
    text: str
    language: str | None
    est_tokens: int
    meta: dict[str, Any]

    @property
    def name(self) -> str: ...


@runtime_checkable
class HistoryEventLike(Protocol):
    """Коммит git или ревизия документа, приведённые к общему виду."""

    at: datetime
    author_hash: str | None
    added: int
    removed: int
    touched_paths: list[str]
    message: str | None


@runtime_checkable
class BundleLike(Protocol):
    assignment_id: str
    stage: str | None
    submitted_at: datetime | None
    deadline_at: datetime | None
    history: list[Any]

    @property
    def solution_files(self) -> list[Any]: ...


@runtime_checkable
class CriterionLike(Protocol):
    id: str
    title: str
    max_score: float
    min_score_for_pass: float | None
    weight: float
    description: str
    checks: list[str]
    anchors: dict[str, str]
    evidence_required: bool
    auto_verifiable: bool
    ai_sensitive: bool


@runtime_checkable
class ScaleLike(Protocol):
    total_max: float
    pass_threshold: float | None
    step: float

    def round_to_step(self, value: float) -> float: ...


@runtime_checkable
class LatePolicyLike(Protocol):
    def apply(
        self, score: float, submitted_at: datetime | None, deadline_at: datetime | None
    ) -> tuple[float, str]: ...


@runtime_checkable
class RubricLike(Protocol):
    assignment_id: str
    title: str
    course: str
    scale: Any
    late_policy: Any
    criteria: list[Any]
    ai_policy: str

    def criterion(self, criterion_id: str) -> Any | None: ...
