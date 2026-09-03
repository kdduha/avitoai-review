"""Разбор JSON рубрики без установленного ядра.

Схема рубрики принадлежит `reviewer-core`. Это упрощённый разбор для демо:
достаточно того, что нужно сервисам по контракту, и ни строкой больше.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any


@dataclass
class Scale:
    total_max: float
    pass_threshold: float | None = None
    step: float = 1.0

    def round_to_step(self, value: float) -> float:
        if self.step <= 0:
            return value
        return round(round(value / self.step) * self.step, 4)


@dataclass
class LatePolicy:
    grace_days: int = 0
    penalty_per_grace_day: float = 0.0
    after_grace: str = "zero"

    def apply(self, score, submitted_at, deadline_at):
        if not submitted_at or not deadline_at or submitted_at <= deadline_at:
            return score, "сдано в срок"
        days = max(1, -(-(submitted_at - deadline_at) // timedelta(days=1)))
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
    assignment_id: str
    title: str = ""
    course: str = ""
    scale: Scale = field(default_factory=lambda: Scale(total_max=10))
    late_policy: LatePolicy = field(default_factory=LatePolicy)
    criteria: list[Criterion] = field(default_factory=list)
    ai_policy: str = "declare_required"

    def criterion(self, criterion_id: str):
        return next((c for c in self.criteria if c.id == criterion_id), None)


def rubric_from_dict(payload: dict[str, Any]) -> Rubric:
    scale_data = payload.get("scale", {})
    late_data = payload.get("late_policy", {})
    return Rubric(
        assignment_id=payload["assignment_id"],
        title=payload.get("title", ""),
        course=payload.get("course", ""),
        scale=Scale(
            total_max=scale_data.get("total_max", 10),
            pass_threshold=scale_data.get("pass_threshold"),
            step=scale_data.get("step", 1.0),
        ),
        late_policy=LatePolicy(
            grace_days=late_data.get("grace_days", 0),
            penalty_per_grace_day=late_data.get("penalty_per_grace", late_data.get(
                "penalty_per_grace_day", 0.0)),
            after_grace=late_data.get("after", late_data.get("after_grace", "zero")),
        ),
        criteria=[
            Criterion(
                id=c["id"],
                title=c["title"],
                max_score=c["max_score"],
                min_score_for_pass=c.get("min_score_for_pass"),
                weight=c.get("weight", 1.0),
                description=c.get("description", ""),
                checks=c.get("checks", []),
                anchors={str(k): v for k, v in c.get("anchors", {}).items()},
                evidence_required=c.get("evidence_required", True),
                auto_verifiable=c.get("auto_verifiable", False),
                ai_sensitive=c.get("ai_sensitive", False),
            )
            for c in payload.get("criteria", [])
        ],
        ai_policy=payload.get("ai_policy", "declare_required"),
    )
