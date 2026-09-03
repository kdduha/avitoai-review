"""Оркестрация детектора."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from llm import PrivacyGateway

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


@dataclass
class DetectionConfig:
    weight_forensics: float = 0.35
    weight_perplexity: float = 0.25
    weight_stylometry: float = 0.15
    weight_judge: float = 0.25
    use_judge: bool = True
    logprob_scorer: Any = None
    ai_sensitive_paths: set[str] = field(default_factory=set)


class DetectionService:
    def __init__(
        self,
        gateway: PrivacyGateway | None = None,
        config: DetectionConfig | None = None,
    ) -> None:
        self.gateway = gateway
        self.config = config or DetectionConfig()

    def analyse(self, bundle: Any) -> DetectionReport:
        artifacts = list(bundle.solution_files)
        cfg = self.config

        signals = [
            forensics.analyse(bundle, weight=cfg.weight_forensics),
            stylometry.analyse(artifacts, weight=cfg.weight_stylometry),
            perplexity.analyse(
                self.gateway, artifacts,
                weight=cfg.weight_perplexity, scorer=cfg.logprob_scorer,
            ),
        ]

        if cfg.use_judge and self.gateway is not None:
            signals.append(judge.analyse(self.gateway, artifacts, weight=cfg.weight_judge))

        report = combine(signals, ai_sensitive_paths=cfg.ai_sensitive_paths)
        self._check_declaration(report, artifacts)
        return report

    # ------------------------------------------------------------------ #

    def _check_declaration(self, report: DetectionReport, artifacts: list[Any]) -> None:
        """Найти декларацию об использовании ИИ.

        Детектор не решает, использовался ли ИИ. Он фиксирует, заявил ли об
        этом студент, — и главным для ревьюера становится не сам сигнал, а
        расхождение: признаки есть, декларации нет.
        """
        for artifact in artifacts:
            for pattern in DECLARATION_PATTERNS:
                match = pattern.search(artifact.text)
                if match:
                    line = artifact.text.count("\n", 0, match.start()) + 1
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
