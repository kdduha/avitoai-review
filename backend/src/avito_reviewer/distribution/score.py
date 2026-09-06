"""Скор пары «работа — ревьюер» и жёсткие ограничения.

Из восьми слагаемых §9.3 считаются шесть. Два не считаются, и это не упущение,
а следствие того, что данных под них нет: косинус по темам требует эмбеддингов,
которых в системе не существует, а преемственность — истории ревью, которой
негде лежать. Подставить вместо них правдоподобную константу значило бы
выдумать сигнал, поэтому терм **отключается**, а не обнуляется: обнулённый терм
неотличим в отчёте от посчитанного и давшего ноль.

Правило доступности одно: **отсутствие данных отключает терм, осмысленное
отсутствие даёт ноль.** Нет профиля — мы не знаем сложности работы, терм
онбординга выключен. Нет прошлого ревьюера — мы знаем, что работа первая, и это
честный ноль.

Доступность решается один раз на весь прогон, а не на пару. Венгерский сравнивает
ячейки по всей матрице, и работа, у которой посчитано пять слагаемых, против
работы с тремя оказались бы на разных шкалах — под давлением ёмкости солвер
систематически предпочитал бы ту, чья шкала выше.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from avito_reviewer.ingest.identity import author_hash

from .schema import (
    Basis,
    Blocked,
    DisabledTerm,
    DistributionItem,
    Reviewer,
    ScoreTerm,
    TermName,
    UnassignedReason,
    Weights,
)

LABELS: dict[TermName, str] = {
    TermName.TOPICS: "Близость по темам",
    TermName.SKILLS: "Покрытие навыками",
    TermName.CONTINUITY: "Тот же ревьюер, что в прошлый раз",
    TermName.TOV: "Тон обратной связи",
    TermName.LOAD: "Загрузка",
    TermName.DEADLINE: "Риск не успеть к сроку",
    TermName.FAIRNESS: "Выравнивание нагрузки",
    TermName.ONBOARDING: "Новичок на сложной работе",
}


@dataclass(slots=True)
class Ledger:
    """Состояние ревьюера по ходу раскладки."""

    reviewer: Reviewer
    committed_before: int = 0
    minutes_assigned: int = 0
    items: int = 0

    @property
    def committed(self) -> int:
        return self.committed_before + self.minutes_assigned

    @property
    def remaining(self) -> int:
        return self.reviewer.capacity_minutes - self.committed

    def ratio(self, extra: int = 0) -> float:
        if self.reviewer.capacity_minutes <= 0:
            return 1.0
        return (self.committed + extra) / self.reviewer.capacity_minutes


@dataclass(slots=True)
class ScoreContext:
    enabled: set[TermName]
    weights: Weights
    now: datetime | None = None
    mean_ratio: float = 0.0
    author_salt: str = ""
    max_items_per_reviewer: int = 0
    _hashes: dict[str, str] = field(default_factory=dict)

    def hash_of(self, handle: str) -> str:
        if handle not in self._hashes:
            self._hashes[handle] = author_hash(handle, salt=self.author_salt)
        return self._hashes[handle]

    @property
    def denominator(self) -> float:
        total = sum(abs(self.weights.of(term)) for term in sorted(self.enabled))
        return total or 1.0


def blocked(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> Blocked | None:
    """Почему этому ревьюеру нельзя отдать эту работу. `None` — можно."""
    if not reviewer.active:
        return Blocked(
            reviewer_id=reviewer.id, reason=UnassignedReason.NOT_ELIGIBLE, detail="не в строю"
        )
    if reviewer.id in item.excluded_reviewer_ids:
        return Blocked(
            reviewer_id=reviewer.id,
            reason=UnassignedReason.EXCLUDED,
            detail="исключён для этой работы",
        )

    conflict = _conflict(reviewer, item, ctx)
    if conflict:
        return Blocked(
            reviewer_id=reviewer.id, reason=UnassignedReason.CONFLICT, detail=conflict
        )

    scope = _out_of_scope(reviewer, item)
    if scope:
        return Blocked(
            reviewer_id=reviewer.id, reason=UnassignedReason.NOT_ELIGIBLE, detail=scope
        )

    limit = reviewer.max_items or ctx.max_items_per_reviewer
    if limit and ledger.items >= limit:
        return Blocked(
            reviewer_id=reviewer.id,
            reason=UnassignedReason.CAPACITY,
            detail=f"уже {ledger.items} работ при пределе {limit}",
        )
    if item.minutes > ledger.remaining:
        return Blocked(
            reviewer_id=reviewer.id,
            reason=UnassignedReason.CAPACITY,
            detail=f"нужно {item.minutes} мин, свободно {max(ledger.remaining, 0)}",
        )
    return None


def _conflict(reviewer: Reviewer, item: DistributionItem, ctx: ScoreContext) -> str:
    if item.student_internal_id and item.student_internal_id in reviewer.conflict_student_ids:
        return "свой студент"
    if reviewer.github_handle and ctx.hash_of(reviewer.github_handle) in item.author_hashes:
        return "соавтор коммитов этой работы"
    return ""


def _out_of_scope(reviewer: Reviewer, item: DistributionItem) -> str:
    if reviewer.course_ids and item.course_id and item.course_id not in reviewer.course_ids:
        return f"не ведёт курс {item.course_id}"
    if reviewer.stream_ids and item.stream_id and item.stream_id not in reviewer.stream_ids:
        return f"не ведёт поток {item.stream_id}"
    if (
        reviewer.assignment_ids
        and item.assignment_id
        and item.assignment_id not in reviewer.assignment_ids
    ):
        return f"не проверяет задание {item.assignment_id}"
    return ""


def enabled_terms(
    items: Sequence[DistributionItem], *, now: datetime | None
) -> tuple[set[TermName], list[DisabledTerm], list[str]]:
    """Какие слагаемые считаются на этом прогоне и почему остальные — нет."""
    enabled: set[TermName] = {TermName.LOAD, TermName.FAIRNESS}
    disabled: list[DisabledTerm] = [
        DisabledTerm(
            term=TermName.TOPICS,
            label=LABELS[TermName.TOPICS],
            reason="нужны эмбеддинги; провайдера нет, вектор тем не считается",
        )
    ]
    limitations: list[str] = []

    profiled = sum(1 for item in items if item.profile is not None)
    if items and profiled == len(items):
        enabled |= {TermName.SKILLS, TermName.ONBOARDING}
    else:
        reason = (
            "ни у одной работы нет профиля"
            if not profiled
            else f"профиль есть у {profiled} работ из {len(items)}"
        )
        disabled += [
            DisabledTerm(term=TermName.SKILLS, label=LABELS[TermName.SKILLS], reason=reason),
            DisabledTerm(
                term=TermName.ONBOARDING, label=LABELS[TermName.ONBOARDING], reason=reason
            ),
        ]
        if profiled:
            limitations.append(
                f"Профиль есть у {profiled} работ из {len(items)}. Слагаемые про навыки и "
                "сложность отключены на весь пакет: иначе баллы работ с профилем и без него "
                "несопоставимы, и под нехваткой ёмкости выигрывали бы первые. Если это важно, "
                "распределите пакеты отдельно."
            )

    dated = sum(1 for item in items if item.due_at is not None)
    if items and dated == len(items) and now is not None:
        enabled.add(TermName.DEADLINE)
    else:
        disabled.append(
            DisabledTerm(
                term=TermName.DEADLINE,
                label=LABELS[TermName.DEADLINE],
                reason="срок известен не у всех работ" if now is not None else "не передано время",
            )
        )

    if any(item.last_reviewer_id for item in items):
        enabled.add(TermName.CONTINUITY)
    else:
        disabled.append(
            DisabledTerm(
                term=TermName.CONTINUITY,
                label=LABELS[TermName.CONTINUITY],
                reason="прошлый ревьюер не передан ни по одной работе",
            )
        )

    if any(item.preferred_tov for item in items):
        enabled.add(TermName.TOV)
    else:
        disabled.append(
            DisabledTerm(
                term=TermName.TOV,
                label=LABELS[TermName.TOV],
                reason="тон обратной связи не запрошен ни по одной работе",
            )
        )

    return enabled, disabled, limitations


def score_terms(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> list[ScoreTerm]:
    """Строки карточки «почему так». Их сумма и есть скор пары."""
    computed = {
        TermName.SKILLS: (_skills, Basis.DECLARED),
        TermName.CONTINUITY: (_continuity, Basis.GIVEN),
        TermName.TOV: (_tov, Basis.DECLARED),
        TermName.LOAD: (_load, Basis.GIVEN),
        TermName.DEADLINE: (_deadline, Basis.GIVEN),
        TermName.FAIRNESS: (_fairness, Basis.GIVEN),
        TermName.ONBOARDING: (_onboarding, Basis.DECLARED),
    }
    terms: list[ScoreTerm] = []
    for term, (fn, basis) in computed.items():
        if term not in ctx.enabled:
            continue
        value, note = fn(reviewer, item, ledger, ctx)
        weight = ctx.weights.of(term)
        terms.append(
            ScoreTerm(
                term=term,
                label=LABELS[term],
                weight=weight,
                value=round(value, 4),
                contribution=round(weight * value / ctx.denominator, 6),
                basis=basis,
                note=note,
            )
        )
    return terms


def total(terms: Sequence[ScoreTerm]) -> float:
    return round(sum(term.contribution for term in terms), 6)


def _skills(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    profile = item.profile
    skills = {s.casefold() for s in reviewer.skills}
    if not skills:
        return 0.0, "навыки в карточке не заполнены"
    needs = {s.casefold() for s in (profile.special_needs if profile else [])}
    themes = {s.casefold() for s in ((profile.topics + profile.stack) if profile else [])}

    parts: list[float] = []
    notes: list[str] = []
    if needs:
        covered = needs & skills
        parts.append(len(covered) / len(needs))
        notes.append(
            "закрыто: " + ", ".join(sorted(covered))
            if covered
            else "не закрыто: " + ", ".join(sorted(needs))
        )
    if themes:
        covered = themes & skills
        parts.append(len(covered) / len(themes))
        if covered:
            notes.append("по темам: " + ", ".join(sorted(covered)))
    if not parts:
        return 0.0, "профиль не назвал ни тем, ни особых требований"
    return sum(parts) / len(parts), "; ".join(notes)


def _continuity(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    if not item.last_reviewer_id:
        return 0.0, "первая работа этого студента — преемственности нет"
    if item.last_reviewer_id == reviewer.id:
        return 1.0, "проверял прошлую работу — увидит динамику"
    return 0.0, "прошлую работу проверял другой"


def _tov(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    if not item.preferred_tov:
        return 0.0, "тон не запрошен"
    if reviewer.tov is None:
        return 0.0, "тон в карточке не указан"
    if reviewer.tov == item.preferred_tov:
        return 1.0, f"тон совпадает: {reviewer.tov.value}"
    return 0.0, f"запрошен {item.preferred_tov.value}, у ревьюера {reviewer.tov.value}"


def _load(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    after = min(max(ledger.ratio(item.minutes), 0.0), 1.0)
    return after, f"после этой работы {after:.0%} недельной ёмкости"


def _deadline(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    if item.due_at is None or ctx.now is None:
        return 0.0, "срок не задан"
    due = item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=UTC)
    left = (due - ctx.now).total_seconds() / 60
    backlog = ledger.minutes_assigned + item.minutes
    if left <= 0:
        return 1.0, "срок уже прошёл"
    risk = min(backlog / left, 1.0)
    return risk, f"{backlog} мин разбора на {int(left)} мин до срока"


def _fairness(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    mine = ledger.ratio(item.minutes)
    value = min(max(0.5 + (ctx.mean_ratio - mine), 0.0), 1.0)
    return value, f"{mine:.0%} против {ctx.mean_ratio:.0%} в среднем по пулу"


def _onboarding(
    reviewer: Reviewer, item: DistributionItem, ledger: Ledger, ctx: ScoreContext
) -> tuple[float, str]:
    if not reviewer.onboarding:
        return 0.0, "не на онбординге"
    complexity = item.profile.complexity if item.profile else 0.0
    return complexity, f"на онбординге, сложность работы {complexity:.2f}"
