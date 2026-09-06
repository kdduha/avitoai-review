"""Оркестрация ревью.

Собирает вместе то, что делают остальные модули: разбивает критерии на
батчи, ходит через шлюз, проверяет цитаты, считает балл.

Устройство подчинено одному требованию: **сбой не должен стоить всей
работы**. Если один батч из четырёх упал — провайдер ответил мусором,
кончились лимиты, оборвалась сеть — ревьюер получает черновик по остальным
критериям и явную отметку о том, каких не хватает. Черновик на три критерия
из четырёх полезнее, чем пустой экран с ошибкой.

На вход идёт не `SubmissionBundle`, а уже собранные тексты артефактов:
дотягивать тела файлов посреди разбора значило бы ходить в сеть из
синхронного кода. Тексты готовит `ai.content` до входа сюда.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from avito_reviewer.ai.content import ArtifactText, gradable_texts
from avito_reviewer.ai.llm import (
    DataClass,
    Identity,
    LLMError,
    LLMUnavailable,
    PrivacyGateway,
    StructuredError,
    TaskKind,
    complete_json,
)
from avito_reviewer.ai.rubric import Criterion, Rubric
from avito_reviewer.config import ReviewOptions

from .aggregate import ScoreBreakdown, aggregate
from .evidence import EvidenceValidator
from .prompts import batch_criteria, build_messages, summary_messages
from .schema import CriterionBatch, CriterionVerdict, ReviewDraft, ReviewSummary

log = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, gateway: PrivacyGateway, options: ReviewOptions | None = None) -> None:
        self.gateway = gateway
        self.options = options or ReviewOptions()


    def review(
        self,
        texts: list[ArtifactText],
        rubric: Rubric,
        *,
        submitted_at: datetime | None = None,
        deadline_at: datetime | None = None,
        gate_facts: list[str] | None = None,
        condition_text: str = "",
        identities: Sequence[Identity] = (),
    ) -> ReviewDraft:
        gradable = gradable_texts(texts)
        validator = EvidenceValidator(gradable)

        criteria = [
            c
            for c in rubric.criteria
            if not (self.options.skip_auto_verifiable and c.auto_verifiable)
        ]

        draft = ReviewDraft(
            assignment_id=rubric.assignment_id,
            rubric_title=rubric.title,
            max_score=rubric.scale.total_max,
            gate_facts=list(gate_facts or []),
            partial_artifacts=[text.path for text in gradable if text.partial],
        )

        with self.gateway.audit.collect() as spend:
            for batch in batch_criteria(criteria, self.options.batch_size):
                verdicts = self._review_batch(
                    batch, rubric, gradable, gate_facts or [], condition_text, draft,
                    identities,
                )
                for verdict in verdicts:
                    criterion = rubric.criterion(verdict.criterion_id)
                    draft.verdicts.append(validator.validate_verdict(verdict, criterion))

            self._fill_missing(draft, criteria)

            breakdown = aggregate(
                draft.verdicts, rubric, submitted_at=submitted_at, deadline_at=deadline_at
            )
            _apply(draft, breakdown)

            draft.attention_reasons = [
                f"{v.criterion_id}: {v.attention_reason}"
                for v in draft.verdicts
                if v.needs_human_attention and v.attention_reason
            ]
            if draft.partial_artifacts:
                draft.attention_reasons.append(
                    "показаны не целиком: " + ", ".join(draft.partial_artifacts)
                )
            draft.needs_human_attention = (
                bool(draft.attention_reasons) or bool(draft.failed_criteria)
            )

            # Резюме — последним: оно пересказывает готовые вердикты и знает
            # итог. Внутри того же блока учёта, иначе его токены не попали бы
            # в стоимость прогона и разбор выглядел бы дешевле, чем обошёлся.
            draft.summary = self._summarise(draft, rubric, identities)

        summary = self.gateway.audit.summary(spend)
        draft.tokens_in = summary["tokens_in"]
        draft.tokens_out = summary["tokens_out"]
        draft.cost_rub = summary["cost_rub"]
        return draft

    def _review_batch(
        self,
        batch: list[Criterion],
        rubric: Rubric,
        texts: list[ArtifactText],
        gate_facts: list[str],
        condition_text: str,
        draft: ReviewDraft,
        identities: Sequence[Identity] = (),
    ) -> list[CriterionVerdict]:
        messages = build_messages(
            rubric, batch, texts, gate_facts=gate_facts, condition_text=condition_text
        )
        try:
            result, _ = complete_json(
                self.gateway,
                messages,
                CriterionBatch,
                task=TaskKind.REVIEW,
                data_class=DataClass.CONTAINS_PD,
                temperature=self.options.temperature,
                max_tokens=self.options.max_tokens,
                identities=identities,
            )
        except (StructuredError, LLMError, LLMUnavailable) as exc:
            # Батч потерян, но остальные критерии ещё можно разобрать.
            ids = [c.id for c in batch]
            log.warning("батч критериев %s не разобран: %s", ids, exc)
            draft.failed_criteria.extend(ids)
            return []

        wanted = {c.id for c in batch}
        verdicts: list[CriterionVerdict] = []
        for verdict in result.verdicts:
            if verdict.criterion_id in wanted:
                verdicts.append(verdict)
            else:
                # Модель придумала критерий или перепутала идентификатор.
                log.warning("модель вернула лишний критерий %s", verdict.criterion_id)
        return verdicts

    def _summarise(
        self, draft: ReviewDraft, rubric: Rubric, identities: Sequence[Identity]
    ) -> ReviewSummary | None:
        """Связный отзыв по уже проставленным вердиктам.

        Не удалось — возвращаем `None`, и черновик приезжает без резюме. Это
        последний шаг, критерии к этому моменту разобраны и подтверждены
        цитатами; ронять из-за него весь прогон было бы обменом целого на
        украшение. Заглушки тоже нет: пустое место честнее выдуманного абзаца.
        """
        if not draft.verdicts:
            return None
        try:
            result, _ = complete_json(
                self.gateway,
                summary_messages(draft, rubric),
                ReviewSummary,
                task=TaskKind.REVIEW,
                data_class=DataClass.CONTAINS_PD,
                temperature=self.options.temperature,
                max_tokens=self.options.max_tokens,
                identities=identities,
            )
        except (StructuredError, LLMError, LLMUnavailable) as exc:
            log.warning("итоговый отзыв не собран: %s", exc)
            return None
        return None if result.is_empty else result

    def _fill_missing(self, draft: ReviewDraft, criteria: list[Criterion]) -> None:
        """Пропущенные критерии — тоже результат, и он должен быть виден.

        Молча выдать черновик на четыре критерия из шести значит показать
        ревьюеру неполную картину как полную. Вместо этого создаём пустой
        вердикт с нулём и явной отметкой: ревьюер сам решит, что с ним делать.
        """
        seen = {v.criterion_id for v in draft.verdicts}
        for criterion in criteria:
            if criterion.id in seen:
                continue
            draft.verdicts.append(
                CriterionVerdict(
                    criterion_id=criterion.id,
                    score=0.0,
                    confidence=0.0,
                    verdict="Критерий не разобран: модель не вернула по нему вердикт.",
                    needs_human_attention=True,
                    attention_reason="вердикт отсутствует — критерий нужно оценить вручную",
                )
            )
            if criterion.id not in draft.failed_criteria:
                draft.failed_criteria.append(criterion.id)

        order = {c.id: i for i, c in enumerate(criteria)}
        draft.verdicts.sort(key=lambda v: order.get(v.criterion_id, len(order)))


def _apply(draft: ReviewDraft, breakdown: ScoreBreakdown) -> None:
    draft.raw_score = breakdown.raw_score
    draft.score = breakdown.final_score
    draft.passed = breakdown.passed
    draft.pass_explanation = breakdown.pass_explanation
    draft.late_explanation = breakdown.late_explanation
