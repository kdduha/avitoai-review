"""Вход в AI-слой: одна сдача — один прогон.

Сервисы ниже синхронные, а дотягивание тел файлов асинхронное, и это не
случайность: сеть должна закончиться до того, как начнётся разбор. Поэтому
здесь два шага — `prepare` собирает тексты (async, ходит к резолверу),
`review` и `detect` считают (sync, в сеть ходят только через шлюз).

Шлюз один на приложение и живёт снаружи: он держит журнал обращений, и
разведение его по запросам потеряло бы сводку по стоимости прогона курса.
Стоимость отдельного ревью при этом считается корректно — по чекпойнту
журнала, а не по всему его содержимому.
"""

from __future__ import annotations

import logging
from datetime import datetime

from avito_reviewer.config import AIConfig
from avito_reviewer.ingest import SubmissionBundle

from .content import ArtifactText, ContentResolver, build_texts
from .detection import DetectionReport, DetectionService
from .llm import PrivacyGateway, gateway_from_config
from .review import ReviewDraft, ReviewService
from .rubric import Rubric

log = logging.getLogger(__name__)


class AIService:
    """Ревью-агент и детектор поверх одного `PrivacyGateway`."""

    def __init__(
        self,
        config: AIConfig,
        *,
        gateway: PrivacyGateway | None = None,
        resolver: ContentResolver | None = None,
        scorer: object | None = None,
    ) -> None:
        self.config = config
        self.gateway = gateway or gateway_from_config(config.llm)
        self.resolver = resolver
        self.review_service = ReviewService(self.gateway, config.review)
        self.detection_service = DetectionService(
            self.gateway, config.detection, scorer=scorer
        )

    async def prepare(self, bundle: SubmissionBundle) -> list[ArtifactText]:
        """Тексты артефактов сдачи, с дозагрузкой тел в пределах бюджета."""
        return await build_texts(bundle, self.resolver, config=self.config.content)

    def review(
        self,
        bundle: SubmissionBundle,
        texts: list[ArtifactText],
        rubric: Rubric,
        *,
        gate_facts: list[str] | None = None,
        condition_text: str = "",
    ) -> ReviewDraft:
        draft = self.review_service.review(
            texts,
            rubric,
            submitted_at=bundle.submitted_at,
            deadline_at=bundle.deadline_at,
            gate_facts=gate_facts,
            condition_text=condition_text,
        )
        log.info(
            "review %s — %.4g/%.4g, цитат у %.0f%% вердиктов, %d токенов, %.2f ₽",
            rubric.assignment_id,
            draft.score,
            draft.max_score,
            draft.evidence_coverage * 100,
            draft.tokens_in + draft.tokens_out,
            draft.cost_rub,
        )
        return draft

    def detect(
        self,
        bundle: SubmissionBundle,
        texts: list[ArtifactText],
        rubric: Rubric | None = None,
    ) -> DetectionReport:
        report = self.detection_service.analyse(bundle, texts)
        if rubric and rubric.ai_sensitive_criteria:
            # Ревьюеру важно, по каким именно критериям сигнал вообще что-то
            # меняет: сгенерированный docker-compose и сгенерированная карта
            # рисков — разные события.
            report.limitations.append(
                "Критерии, чувствительные к самостоятельности: "
                + ", ".join(c.id for c in rubric.ai_sensitive_criteria)
            )
        log.info(
            "detect %s — %s (%.2f), сигналов %d из %d",
            bundle.origin_url,
            report.label,
            report.overall_score,
            len(report.available_signals),
            len(report.signals),
        )
        return report

    @property
    def cost_summary(self) -> dict[str, object]:
        """Сводка по всем обращениям к моделям с момента старта приложения."""
        return self.gateway.audit.summary()
