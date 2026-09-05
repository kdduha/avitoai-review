"""Раскладка работ по ревьюерам: чистая функция без сети, модели и часов.

Почему не одна большая матрица. Ёмкость меряется в минутах, а не в слотах, то
есть точная задача — обобщённое назначение, NP-трудное; ни венгерский, ни
min-cost flow его не выражают. Но важнее второе: **целевая функция не
разделима**. `load_ratio` и `fairness_bonus` зависят от того распределения,
которое ещё строится, и одна матрица посчитала бы их по входящей загрузке —
сильный ревьюер оставался бы привлекательным и после десятой работы. Это был бы
глобальный оптимум не той функции.

Отсюда раунды: раунд — одна работа на ревьюера, между раундами скор
пересчитывается по новому состоянию. Внутри раунда — честный оптимум задачи о
назначениях; по плану целиком оптимальность не заявляется, и в докстринге
`DistributionPlan` это сказано прямо.

Работа не может пропасть молча: `len(allocations) + len(unassigned)` всегда
равно числу поданных работ, и каждая нераспределённая называет поимённо всех,
кто её не взял, — иначе координатор узнаёт о ней от студента через неделю.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime

from .hungarian import INFEASIBLE, solve
from .schema import (
    Allocation,
    Alternative,
    Blocked,
    DistributionItem,
    DistributionPlan,
    Reviewer,
    ReviewerLoad,
    ScoreTerm,
    Unassigned,
    UnassignedReason,
    Weights,
)
from .score import Ledger, ScoreContext, blocked, enabled_terms, score_terms, total

log = logging.getLogger(__name__)

COST_SCALE = 1000
_IDLE = INFEASIBLE // 2
"""Стоимость простоя. Хуже любой настоящей пары и лучше запрещённой: ревьюер
предпочтёт даже неудачную работу безделью, но не возьмёт ту, которую нельзя."""


def distribute(
    items: Sequence[DistributionItem],
    reviewers: Sequence[Reviewer],
    *,
    committed_minutes: Mapping[str, int] | None = None,
    weights: Weights | None = None,
    now: datetime | None = None,
    max_items_per_reviewer: int = 0,
    alternatives: int = 2,
    author_salt: str = "",
) -> DistributionPlan:
    """Разложить работы по ревьюерам. Один и тот же вход даёт один и тот же план."""
    items = sorted(items, key=lambda i: i.item_id)
    reviewers = sorted(reviewers, key=lambda r: r.id)
    load = dict(committed_minutes or {})

    enabled, disabled, limitations = enabled_terms(items, now=now)
    ctx = ScoreContext(
        enabled=enabled,
        weights=weights or Weights(),
        now=now,
        author_salt=author_salt,
        max_items_per_reviewer=max_items_per_reviewer,
    )
    limitations += _salt_note(items, reviewers, author_salt)

    ledgers = {r.id: Ledger(reviewer=r, committed_before=load.get(r.id, 0)) for r in reviewers}
    plan = DistributionPlan(
        enabled_terms=sorted(enabled, key=lambda t: t.value),
        disabled_terms=disabled,
        limitations=limitations,
        items=len(items),
        reviewers=len(reviewers),
    )

    pending = list(items)
    if not reviewers:
        plan.unassigned = [
            Unassigned(
                item_id=item.item_id,
                est_review_minutes=item.minutes,
                reason=UnassignedReason.NO_REVIEWERS,
                detail="в пуле нет ни одного ревьюера",
            )
            for item in pending
        ]
        return plan

    pending = _apply_pins(pending, ledgers, ctx, plan)

    rounds = 0
    while pending:
        rounds += 1
        pending, committed = _round(pending, ledgers, ctx, plan, rounds, alternatives)
        if not committed:
            break
    plan.rounds = rounds

    for item in pending:
        plan.unassigned.append(_refuse(item, ledgers, ctx))

    plan.allocations.sort(key=lambda a: a.item_id)
    plan.unassigned.sort(key=lambda u: u.item_id)
    plan.loads = [_load_of(ledgers[r.id]) for r in reviewers]
    log.info(
        "distribute: %d работ на %d ревьюеров — распределено %d за %d раундов, без ревьюера %d",
        plan.items,
        plan.reviewers,
        len(plan.allocations),
        plan.rounds,
        len(plan.unassigned),
    )
    return plan


# --------------------------------------------------------------------------- #

def _round(
    pending: list[DistributionItem],
    ledgers: dict[str, Ledger],
    ctx: ScoreContext,
    plan: DistributionPlan,
    number: int,
    alternatives: int,
) -> tuple[list[DistributionItem], int]:
    ctx.mean_ratio = _mean_ratio(ledgers)

    feasible = [r for r in _active(ledgers) if any(not blocked(r, i, ledgers[r.id], ctx) for i in pending)]
    if not feasible:
        return pending, 0

    terms: dict[tuple[str, str], list[ScoreTerm]] = {}
    scores: dict[tuple[str, str], float] = {}
    cost: list[list[int]] = []
    for reviewer in feasible:
        row: list[int] = []
        for item in pending:
            if blocked(reviewer, item, ledgers[reviewer.id], ctx):
                row.append(INFEASIBLE)
                continue
            pair = score_terms(reviewer, item, ledgers[reviewer.id], ctx)
            value = total(pair)
            terms[(reviewer.id, item.item_id)] = pair
            scores[(reviewer.id, item.item_id)] = value
            row.append(-round(value * COST_SCALE))
        cost.append(row)

    padding = max(0, len(feasible) - len(pending))
    if padding:
        for row in cost:
            row.extend([_IDLE] * padding)

    taken = 0
    for index, column in enumerate(solve(cost)):
        if column < 0 or column >= len(pending) or cost[index][column] >= _IDLE:
            continue
        reviewer, item = feasible[index], pending[column]
        plan.allocations.append(
            Allocation(
                item_id=item.item_id,
                reviewer_id=reviewer.id,
                reviewer_name=reviewer.name,
                est_review_minutes=item.minutes,
                score=scores[(reviewer.id, item.item_id)],
                explain=terms[(reviewer.id, item.item_id)],
                alternatives=_runners_up(
                    item, reviewer.id, feasible, scores, alternatives
                ),
                round=number,
            )
        )
        taken += 1

    assigned = {a.item_id for a in plan.allocations}
    for allocation in plan.allocations:
        if allocation.round == number:
            ledger = ledgers[allocation.reviewer_id]
            ledger.minutes_assigned += allocation.est_review_minutes
            ledger.items += 1
    return [item for item in pending if item.item_id not in assigned], taken


def _apply_pins(
    pending: list[DistributionItem],
    ledgers: dict[str, Ledger],
    ctx: ScoreContext,
    plan: DistributionPlan,
) -> list[DistributionItem]:
    """Закреплённые работы уходят до раскладки и съедают ёмкость.

    Закрепление не отменяет жёстких ограничений: пин, прячущий соавторство или
    не влезающий в ёмкость, становится нераспределённой работой, а не тихим
    исключением из правил.
    """
    rest: list[DistributionItem] = []
    ctx.mean_ratio = _mean_ratio(ledgers)
    for item in pending:
        if not item.pinned_reviewer_id:
            rest.append(item)
            continue
        ledger = ledgers.get(item.pinned_reviewer_id)
        if ledger is None:
            plan.unassigned.append(
                Unassigned(
                    item_id=item.item_id,
                    est_review_minutes=item.minutes,
                    reason=UnassignedReason.PIN_INFEASIBLE,
                    detail=f"закреплён {item.pinned_reviewer_id}, которого нет в пуле",
                )
            )
            continue
        refusal = blocked(ledger.reviewer, item, ledger, ctx)
        if refusal:
            plan.unassigned.append(
                Unassigned(
                    item_id=item.item_id,
                    est_review_minutes=item.minutes,
                    reason=UnassignedReason.PIN_INFEASIBLE,
                    detail=f"закреплён {ledger.reviewer.id}, но {refusal.detail}",
                    blocked_by=[refusal],
                )
            )
            continue
        pair = score_terms(ledger.reviewer, item, ledger, ctx)
        plan.allocations.append(
            Allocation(
                item_id=item.item_id,
                reviewer_id=ledger.reviewer.id,
                reviewer_name=ledger.reviewer.name,
                est_review_minutes=item.minutes,
                score=total(pair),
                explain=pair,
                round=0,
                pinned=True,
            )
        )
        ledger.minutes_assigned += item.minutes
        ledger.items += 1
    return rest


def _refuse(
    item: DistributionItem, ledgers: dict[str, Ledger], ctx: ScoreContext
) -> Unassigned:
    refusals: list[Blocked] = []
    for ledger in ledgers.values():
        refusal = blocked(ledger.reviewer, item, ledger, ctx)
        if refusal:
            refusals.append(refusal)
    return Unassigned(
        item_id=item.item_id,
        est_review_minutes=item.minutes,
        reason=_dominant(refusals),
        detail=_detail(item, refusals),
        blocked_by=sorted(refusals, key=lambda b: b.reviewer_id),
    )


def _dominant(refusals: Sequence[Blocked]) -> UnassignedReason:
    """Причина, которую координатор может починить.

    Нехватка ёмкости чинится: поднять капасити, снять чужую работу. Конфликт не
    чинится вовсе. Поэтому если хоть кого-то остановила только ёмкость — это
    ёмкость, и координатор увидит действие, а не приговор.
    """
    if not refusals:
        return UnassignedReason.NO_REVIEWERS
    reasons = {r.reason for r in refusals}
    if UnassignedReason.CAPACITY in reasons:
        return UnassignedReason.CAPACITY
    if reasons == {UnassignedReason.CONFLICT}:
        return UnassignedReason.CONFLICT
    if reasons == {UnassignedReason.EXCLUDED}:
        return UnassignedReason.EXCLUDED
    return UnassignedReason.NOT_ELIGIBLE


def _detail(item: DistributionItem, refusals: Sequence[Blocked]) -> str:
    if not refusals:
        return "ревьюеров в пуле нет"
    counts: dict[UnassignedReason, int] = {}
    for refusal in refusals:
        counts[refusal.reason] = counts.get(refusal.reason, 0) + 1
    parts = [f"{_REASON_WORD[reason]}: {count}" for reason, count in sorted(counts.items())]
    return f"{item.minutes} мин не взял никто из {len(refusals)} — " + ", ".join(parts)


_REASON_WORD: dict[UnassignedReason, str] = {
    UnassignedReason.NO_REVIEWERS: "пул пуст",
    UnassignedReason.CONFLICT: "конфликт интересов",
    UnassignedReason.CAPACITY: "не хватает ёмкости",
    UnassignedReason.NOT_ELIGIBLE: "не ведёт этот курс",
    UnassignedReason.EXCLUDED: "исключён вручную",
    UnassignedReason.PIN_INFEASIBLE: "закрепление невозможно",
}


def _runners_up(
    item: DistributionItem,
    chosen: str,
    reviewers: Sequence[Reviewer],
    scores: Mapping[tuple[str, str], float],
    limit: int,
) -> list[Alternative]:
    others = [
        Alternative(
            reviewer_id=r.id, reviewer_name=r.name, score=scores[(r.id, item.item_id)]
        )
        for r in reviewers
        if r.id != chosen and (r.id, item.item_id) in scores
    ]
    others.sort(key=lambda a: (-a.score, a.reviewer_id))
    return others[: max(limit, 0)]


def _active(ledgers: Mapping[str, Ledger]) -> list[Reviewer]:
    return [
        ledger.reviewer
        for key in sorted(ledgers)
        if (ledger := ledgers[key]).reviewer.active and ledger.remaining > 0
    ]


def _mean_ratio(ledgers: Mapping[str, Ledger]) -> float:
    active = [ledger for ledger in ledgers.values() if ledger.reviewer.active]
    if not active:
        return 0.0
    return sum(ledger.ratio() for ledger in active) / len(active)


def _load_of(ledger: Ledger) -> ReviewerLoad:
    return ReviewerLoad(
        reviewer_id=ledger.reviewer.id,
        name=ledger.reviewer.name,
        onboarding=ledger.reviewer.onboarding,
        capacity_minutes=ledger.reviewer.capacity_minutes,
        committed_before=ledger.committed_before,
        items=ledger.items,
        minutes_assigned=ledger.minutes_assigned,
        load_ratio_before=round(
            ledger.committed_before / ledger.reviewer.capacity_minutes, 4
        )
        if ledger.reviewer.capacity_minutes
        else 0.0,
        load_ratio_after=round(ledger.ratio(), 4),
        remaining_minutes=max(ledger.remaining, 0),
    )


def _salt_note(
    items: Sequence[DistributionItem], reviewers: Sequence[Reviewer], salt: str
) -> list[str]:
    if salt:
        return []
    if not any(item.author_hashes for item in items):
        return []
    if not any(reviewer.github_handle for reviewer in reviewers):
        return []
    return [
        "Соль псевдонимизации пустая (INGEST_AUTHOR_SALT). Совпадение по author_hash "
        "остаётся верным, но несолёный хеш подбирается по логину — как признак "
        "конфликта интересов он слабее, чем выглядит."
    ]
