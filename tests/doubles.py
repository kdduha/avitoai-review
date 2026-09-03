"""Лёгкие двойники моделей ядра.

Сервисы работают с ядром по структурным протоколам из `contracts.py`, поэтому
тестам не нужен установленный `reviewer-core`: достаточно объектов нужной
формы. Побочная польза — если двойники перестанут подходить, значит контракт
разъехался, и это видно сразу, а не на интеграции.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class Locator:
    start_line: int | None = None
    end_line: int | None = None
    page: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    notebook_cell: int | None = None


@dataclass
class Segment:
    index: int = 0
    start: int = 0
    end: int = 0
    locator: Locator = field(default_factory=Locator)


@dataclass
class Artifact:
    path: str
    text: str
    id: str = "a1"
    language: str | None = None
    est_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.split("/")[-1]


@dataclass
class HistoryEvent:
    at: datetime
    added: int = 0
    removed: int = 0
    author_hash: str | None = "author1"
    touched_paths: list[str] = field(default_factory=list)
    message: str | None = None
    source: str = "git"


@dataclass
class Bundle:
    assignment_id: str = "demo"
    stage: str | None = None
    submitted_at: datetime | None = None
    deadline_at: datetime | None = None
    files: list[Artifact] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)

    @property
    def solution_files(self) -> list[Artifact]:
        return self.files


@dataclass
class Scale:
    total_max: float = 10.0
    pass_threshold: float | None = 6.0
    step: float = 0.5

    def round_to_step(self, value: float) -> float:
        if self.step <= 0:
            return value
        return round(round(value / self.step) * self.step, 4)


@dataclass
class LatePolicy:
    grace_days: int = 1
    penalty_per_grace_day: float = 1.0
    after_grace: str = "zero"

    def apply(self, score, submitted_at, deadline_at):
        if not submitted_at or not deadline_at or submitted_at <= deadline_at:
            return score, "сдано в срок"
        late = submitted_at - deadline_at
        days = max(1, -(-late // timedelta(days=1)))
        if days <= self.grace_days:
            penalty = self.penalty_per_grace_day * days
            return max(0.0, score - penalty), f"просрочка {days} дн., штраф −{penalty:g}"
        if self.after_grace == "zero":
            return 0.0, f"просрочка {days} дн. — 0 баллов"
        return max(0.0, score - self.penalty_per_grace_day * days), f"просрочка {days} дн."


@dataclass
class Criterion:
    id: str
    title: str
    max_score: float
    min_score_for_pass: float | None = None
    weight: float = 1.0
    description: str = ""
    checks: list[str] = field(default_factory=list)
    anchors: dict[str, str] = field(default_factory=dict)
    evidence_required: bool = True
    auto_verifiable: bool = False
    ai_sensitive: bool = False


@dataclass
class Rubric:
    assignment_id: str = "demo"
    title: str = "Демо-задание"
    course: str = "Демо-курс"
    scale: Scale = field(default_factory=Scale)
    late_policy: LatePolicy = field(default_factory=LatePolicy)
    criteria: list[Criterion] = field(default_factory=list)
    ai_policy: str = "declare_required"

    def criterion(self, criterion_id: str):
        return next((c for c in self.criteria if c.id == criterion_id), None)


# --------------------------------------------------------------------------- #

GO_MAIN = """package main

import (
\t"log"
\t"net/http"
\t"os/signal"
)

func main() {
\tr := chi.NewRouter()
\tr.Get("/ping", handlePing)
\tr.Head("/healthcheck", handleHealth)

\tsignal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
\t<-stop
\tlog.Println("Shutting down service-courier")
}

func handlePing(w http.ResponseWriter, r *http.Request) {
\tw.WriteHeader(http.StatusOK)
\tw.Write([]byte(`{"message":"pong"}`))
}
"""


def go_bundle(**kwargs) -> Bundle:
    now = datetime(2026, 2, 8, 20, 0, tzinfo=timezone.utc)
    defaults = dict(
        assignment_id="go-task1",
        submitted_at=now,
        deadline_at=now + timedelta(days=1),
        files=[Artifact(path="cmd/main.go", text=GO_MAIN, id="art-main", language="go")],
    )
    defaults.update(kwargs)
    return Bundle(**defaults)


def go_rubric(**kwargs) -> Rubric:
    defaults = dict(
        assignment_id="go-task1",
        title="Boilerplate сервиса на Go",
        scale=Scale(total_max=6, pass_threshold=4, step=0.5),
        criteria=[
            Criterion(
                id="c1", title="Структура проекта", max_score=2, min_score_for_pass=1,
                checks=["код разделён на cmd/ и internal/"],
            ),
            Criterion(
                id="c2", title="Тестовые эндпоинты", max_score=2, min_score_for_pass=1,
                checks=["GET /ping возвращает 200", "HEAD /healthcheck возвращает 204"],
            ),
            Criterion(
                id="c3", title="Корректное завершение", max_score=2,
                checks=["в лог пишется Shutting down service-courier"],
            ),
        ],
    )
    defaults.update(kwargs)
    return Rubric(**defaults)
