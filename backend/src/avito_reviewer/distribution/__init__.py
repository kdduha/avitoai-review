"""Распределение работ по ревьюерам.

Разделение труда из §9.1: **модель говорит, что это за работа, код решает, кому
её отдать.** Профиль работы строит LLM один раз на сдачу (`profile.py`); выбор
ревьюера — детерминированный солвер, который к модели не ходит вовсе. Это не
эстетика: координатор обязан уметь объяснить студенту, почему его проверяет
именно этот человек, а вероятностный ответ на такой вопрос не годится.

Домен называется `distribution`, потому что `assignment` в этом коде — задание.
"""

from .roster import ReviewerRejected, ReviewerStore, load_reviewer, validate_reviewer
from .schema import (
    Allocation,
    Alternative,
    Basis,
    Blocked,
    DisabledTerm,
    DistributionItem,
    DistributionPlan,
    Reviewer,
    ReviewerLoad,
    ScoreTerm,
    TermName,
    Tov,
    Unassigned,
    UnassignedReason,
    Weights,
    WorkProfile,
)
from .solver import distribute

__all__ = [
    "Allocation",
    "Alternative",
    "Basis",
    "Blocked",
    "DisabledTerm",
    "DistributionItem",
    "DistributionPlan",
    "Reviewer",
    "ReviewerLoad",
    "ReviewerRejected",
    "ReviewerStore",
    "ScoreTerm",
    "TermName",
    "Tov",
    "Unassigned",
    "UnassignedReason",
    "Weights",
    "WorkProfile",
    "distribute",
    "load_reviewer",
    "validate_reviewer",
]
