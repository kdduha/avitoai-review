"""Оркестрация детектора.

На вход идут и `SubmissionBundle` — форензике нужна история ревизий, — и
готовые тексты артефактов: остальные три сигнала смотрят на то, как работа
написана. Что из текстов доступно целиком, а что фрагментом, решает
`ai.content`; здесь это только учитывается.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from avito_reviewer.ai.content import ArtifactText, solution_texts
from avito_reviewer.ai.llm import Identity, PrivacyGateway
from avito_reviewer.config import DetectionOptions
from avito_reviewer.ingest import SubmissionBundle

from .ensemble import combine
from .schema import DetectionReport
from .signals import forensics, judge, perplexity, stylometry

# Как студенты обычно оформляют декларацию об использовании ИИ. Условие
# product_fraud требует её прямо: «Если вы использовали ИИ — укажите это в
# работе и опишите, как именно».
DECLARATION_PATTERNS = [
    re.compile(r"использов\w*\s+(ии|ai|нейросет\w*|gpt|chatgpt|claude|llm|яндекс gpt|gigachat)", re.I),
    re.compile(r"(ии|ai)[-\s]инструмент", re.I),
    re.compile(r"с\s+помощью\s+(нейросет\w*|chatgpt|gpt|ии)", re.I),
    re.compile(r"(сгенерирован\w*|написан\w*)\s+(с помощью|при помощи)\s+\w*(gpt|ии|ai)", re.I),
]


class DetectionService:
    def __init__(
        self,
        gateway: PrivacyGateway | None = None,
        options: DetectionOptions | None = None,
        *,
        scorer: object | None = None,
        ai_sensitive_paths: set[str] | None = None,
    ) -> None:
        self.gateway = gateway
        self.options = options or DetectionOptions()
        self.scorer = scorer
        self.ai_sensitive_paths = ai_sensitive_paths or set()

    def analyse(
        self,
        bundle: SubmissionBundle,
        texts: list[ArtifactText],
        identities: Sequence[Identity] = (),
    ) -> DetectionReport:
        # `tooling` и `noise` исключены и отсюда тоже: сгенерированный
        # Dockerfile ничего не говорит о самостоятельности студента.
        studied = solution_texts(texts)
        options = self.options

        if self.gateway is None:
            return self._run(bundle, studied, spend=None)

        # Подписка открывается до первого сигнала: перплексия со своим scorer
        # тоже ходит к модели, и её токены — часть стоимости этого прогона.
        with self.gateway.audit.collect() as spend:
            return self._run(bundle, studied, spend=spend, identities=identities)

    def _run(self, bundle, studied, *, spend, identities: Sequence[Identity] = ()) -> DetectionReport:
        options = self.options
        signals = [
            forensics.analyse(bundle, weight=options.weight_forensics),
            stylometry.analyse(studied, weight=options.weight_stylometry),
            perplexity.analyse(
                self.gateway,
                studied,
                weight=options.weight_perplexity,
                scorer=self.scorer,
            ),
        ]
        if options.use_judge and self.gateway is not None:
            signals.append(judge.analyse(self.gateway, studied, weight=options.weight_judge, identities=identities))

        report = combine(signals, ai_sensitive_paths=self.ai_sensitive_paths)
        self._note_partial(report, studied)
        self._check_declaration(report, studied)

        if spend is not None and self.gateway is not None:
            summary = self.gateway.audit.summary(spend)
            report.tokens_in = int(summary["tokens_in"])
            report.tokens_out = int(summary["tokens_out"])
            report.cost_rub = float(summary["cost_rub"])
        return report

    # ------------------------------------------------------------------ #

    def _note_partial(self, report: DetectionReport, texts: list[ArtifactText]) -> None:
        """Неполные файлы — ограничение проверки, а не деталь реализации."""
        partial = [text.path for text in texts if text.partial]
        if partial:
            report.limitations.append(
                "Доступны только фрагментами (полный текст не загружался): "
                + ", ".join(partial[:8])
                + ". Статистические сигналы по ним не считались."
            )

    def _check_declaration(self, report: DetectionReport, texts: list[ArtifactText]) -> None:
        """Найти декларацию об использовании ИИ.

        Детектор не решает, использовался ли ИИ. Он фиксирует, заявил ли об
        этом студент, — и главным для ревьюера становится не сам сигнал, а
        расхождение: признаки есть, декларации нет.
        """
        for artifact in texts:
            for pattern in DECLARATION_PATTERNS:
                match = pattern.search(artifact.text)
                if match:
                    index = artifact.text.count("\n", 0, match.start())
                    line = (
                        artifact.line_numbers[index]
                        if index < len(artifact.line_numbers)
                        else index + 1
                    )
                    excerpt = _line_at(artifact.text, match.start())
                    report.declared_ai_usage = True
                    report.declaration_note = (
                        f"Студент заявил использование ИИ ({artifact.path}:{line}): «{excerpt}». "
                        f"Сверьте описанное с найденными фрагментами."
                    )
                    return

        report.declared_ai_usage = False
        if report.overall_score >= 0.5:
            report.declaration_note = (
                "Декларация об использовании ИИ в работе не найдена, при этом "
                "сигналы присутствуют. По условию задания использование ИИ "
                "требуется указывать — это расхождение, а не нарушение само по себе."
            )
        else:
            report.declaration_note = "Декларация об использовании ИИ не найдена."


def _line_at(text: str, position: int, limit: int = 160) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    end = len(text) if end == -1 else end
    return text[start:end].strip()[:limit]
