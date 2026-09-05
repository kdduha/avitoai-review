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

from avito_reviewer.config import AIConfig
from avito_reviewer.ingest import SubmissionBundle

from . import gate
from .content import ArtifactText, ContentResolver, build_texts
from .detection import DetectionReport, DetectionService
from .detection.signals.perplexity import LogprobScorer
from .llm import Identity, PrivacyGateway, gateway_from_config
from .llm.audit import Spend
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
        scorer: LogprobScorer | None = None,
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

    @staticmethod
    def identities(bundle: SubmissionBundle, student_name: str | None = None) -> list[Identity]:
        """Кого скрабер обязан вычистить точно, а не по совпадению шаблона.

        Логины лежат в бандле, поэтому закрываются всегда: `student-1043` стоит
        в каждой строке импорта, и полагаться тут на общие правила незачем.
        Имени в `StudentRef` нет намеренно — его подставляет платформа, когда
        знает; без него имя остаётся на общих детекторах.
        """
        return [
            Identity(
                role="student",
                name=student_name,
                handles=tuple(bundle.student_ref.external_handles.values()),
            )
        ]

    def review(
        self,
        bundle: SubmissionBundle,
        texts: list[ArtifactText],
        rubric: Rubric,
        *,
        gate_facts: list[str] | None = None,
        condition_text: str = "",
        student_name: str | None = None,
    ) -> ReviewDraft:
        # Формальные проверки идут первыми и не стоят токенов. Если работа не
        # принимается по формату, модель не запускается вовсе — ревьюер и так
        # вернёт её студенту.
        checks = gate.run(bundle, texts, rubric)
        facts = list(gate_facts or []) + checks.facts

        if checks.blocked:
            reason = "не пройдены формальные требования: " + "; ".join(
                outcome.label for outcome in checks.failures if outcome.level == "blocking"
            )
            draft = self.review_service.without_model(
                rubric,
                reason,
                submitted_at=bundle.submitted_at,
                deadline_at=bundle.deadline_at,
            )
        else:
            draft = self.review_service.review(
                texts,
                rubric,
                submitted_at=bundle.submitted_at,
                deadline_at=bundle.deadline_at,
                gate_facts=facts,
                condition_text=condition_text,
                identities=self.identities(bundle, student_name),
            )

        draft.gate = checks
        draft.gate_facts = facts
        log.info(
            "review %s [%s] — %.4g/%.4g, цитат у %.0f%% вердиктов, %d токенов, %.2f ₽",
            rubric.assignment_id,
            checks.status.value,
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
        *,
        student_name: str | None = None,
    ) -> DetectionReport:
        report = self.detection_service.analyse(bundle, texts, self.identities(bundle, student_name))
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
    def cost_summary(self) -> Spend:
        """Сводка по всем обращениям к моделям с момента старта приложения."""
        return self.gateway.audit.summary()
