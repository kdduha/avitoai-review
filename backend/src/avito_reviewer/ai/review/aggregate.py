"""Подсчёт итогового балла.

Единственное место, где появляется итоговая оценка, и модель сюда не
допускается: балл должен быть воспроизводимым, а объяснение «почему 62, а не 65»
— собираться из слагаемых.

Порядок операций зафиксирован:

    сумма с весами → округление по шагу шкалы → порог зачёта
    → обязательные минимумы по критериям → штраф за просрочку

Штраф последний, потому что по условиям курсов применяется к итоговой оценке, а
не к критериям. Обязательные минимумы стоят до него: провал по обязательному
критерию — незачёт по существу работы, и просрочка тут ни при чём.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from avito_reviewer.ai.rubric import Rubric

from .schema import CriterionVerdict


@dataclass
class ScoreBreakdown:
    """Разбор итога по слагаемым — то, что показывается в карточке «почему столько»."""

    raw_score: float = 0.0
    rounded_score: float = 0.0
    final_score: float = 0.0
    max_score: float = 0.0
    passed: bool | None = None
    """`None` — рубрика не задаёт порога, и решает ревьюер.

    Раньше здесь стояло `True`: работа с обнулённым за просрочку баллом
    показывалась как «зачёт, 0 из 7». Порог, которого нет в условии, нельзя
    ни пройти, ни не пройти."""
    pass_explanation: str = ""
    late_explanation: str = ""
    contributions: list[dict[str, Any]] = field(default_factory=list)
    failed_minimums: list[str] = field(default_factory=list)


def aggregate(
    verdicts: list[CriterionVerdict],
    rubric: Rubric,
    *,
    submitted_at: datetime | None = None,
    deadline_at: datetime | None = None,
) -> ScoreBreakdown:
    breakdown = ScoreBreakdown(max_score=rubric.scale.total_max)

    total = 0.0
    for verdict in verdicts:
        criterion = rubric.criterion(verdict.criterion_id)
        if criterion is None:
            # Критерия нет в рубрике: в сумму не идёт, но и молча пропасть не должен.
            breakdown.contributions.append(
                {
                    "criterion_id": verdict.criterion_id,
                    "title": "критерий отсутствует в рубрике",
                    "score": verdict.score,
                    "max_score": 0.0,
                    "weight": 0.0,
                    "contribution": 0.0,
                    "counted": False,
                }
            )
            continue

        weight = criterion.weight or 1.0
        contribution = verdict.score * weight
        total += contribution

        breakdown.contributions.append(
            {
                "criterion_id": criterion.id,
                "title": criterion.title,
                "score": verdict.score,
                "max_score": criterion.max_score,
                "weight": weight,
                "contribution": round(contribution, 4),
                "counted": True,
                "needs_human_attention": verdict.needs_human_attention,
            }
        )

        minimum = criterion.min_score_for_pass
        if minimum is not None and verdict.score < minimum:
            breakdown.failed_minimums.append(
                f"{criterion.id} «{criterion.title}»: {verdict.score:g} при обязательном минимуме {minimum:g}"
            )

    breakdown.raw_score = round(total, 4)
    breakdown.rounded_score = rubric.scale.round_to_step(total)

    # Штраф за просрочку по правилу из условия задания.
    final, late_note = rubric.late_policy.apply(
        breakdown.rounded_score, submitted_at, deadline_at
    )
    breakdown.final_score = rubric.scale.round_to_step(final)
    breakdown.late_explanation = late_note

    breakdown.passed, breakdown.pass_explanation = _decide(breakdown, rubric)
    return breakdown


def _decide(breakdown: ScoreBreakdown, rubric: Rubric) -> tuple[bool | None, str]:
    """Зачёт — не только про сумму.

    В системном дизайне у части критериев есть колонка «мин. балл»: провал по
    обязательному критерию не компенсируется набранным на остальных. Свести
    зачёт к порогу по сумме значило бы потерять это правило.

    Порога нет в условии — вердикта нет: `None`, а не «зачёт». Иначе работа,
    обнулённая штрафом за просрочку, объявлялась зачтённой с нулём баллов.
    """
    if breakdown.failed_minimums:
        return False, "не набран обязательный минимум: " + "; ".join(breakdown.failed_minimums)

    threshold = rubric.scale.pass_threshold
    if threshold is None:
        return None, "порога зачёта в рубрике нет — решение за ревьюером"

    if breakdown.final_score >= threshold:
        return True, f"{breakdown.final_score:g} из {breakdown.max_score:g} при пороге {threshold:g}"

    return False, f"{breakdown.final_score:g} из {breakdown.max_score:g} при пороге {threshold:g}"


def explain(breakdown: ScoreBreakdown) -> str:
    """Текстовое объяснение итога для карточки ревьюера."""
    lines = [f"{'критерий':<8} {'балл':>10}  {'вклад':>8}  название"]
    for item in breakdown.contributions:
        score = f"{item['score']:g}/{item['max_score']:g}" if item["counted"] else "—"
        flag = " ⚠" if item.get("needs_human_attention") else ""
        lines.append(
            f"{item['criterion_id']:<8} {score:>10}  {item['contribution']:>8.2f}  {item['title']}{flag}"
        )

    lines.append("")
    lines.append(f"сумма с весами: {breakdown.raw_score:g}")
    if breakdown.rounded_score != breakdown.raw_score:
        lines.append(f"округление по шагу шкалы: {breakdown.rounded_score:g}")
    if breakdown.final_score != breakdown.rounded_score:
        lines.append(f"после штрафа за срок: {breakdown.final_score:g} ({breakdown.late_explanation})")
    outcome = {True: "зачёт", False: "незачёт", None: "решает ревьюер"}[breakdown.passed]
    lines.append(f"итог: {outcome} — {breakdown.pass_explanation}")
    return "\n".join(lines)
