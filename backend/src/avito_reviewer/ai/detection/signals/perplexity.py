"""Перплексия на локальной модели.

Сигнал опциональный: требует локального сервинга, отдающего logprobs. Наружу
эта задача не уходит никогда — внешние провайдеры логпробы почти не отдают,
объём токенов велик, а стоить он должен ноль.

Меряем две вещи по скользящему окну:

* **среднюю неожиданность** — сгенерированный текст модель предсказывает
  слишком хорошо;
* **burstiness** — разброс неожиданности между соседними окнами. У человека
  текст рваный: сложная мысль, простая, отступление. У модели ровный.

Второе важнее первого. Низкая перплексия сама по себе бывает у чистого
формального текста, написанного человеком; ровная низкая перплексия на
протяжении всей работы — гораздо более специфичный признак.

Без настроенного локального провайдера сигнал честно сообщает, что
недоступен, и ансамбль перераспределяет веса. Тихо занулять его нельзя:
отсутствие сигнала и отсутствие признаков — разные вещи. По той же причине
пропускаются файлы, доступные фрагментом: скользящее окно по склейке обрывков
меряет наши разрывы, а не текст студента.
"""

from __future__ import annotations

import logging
import statistics

from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.llm import LLMError, LLMUnavailable, PrivacyGateway

from ..schema import SignalKind, SignalResult, SignalStatus, Span

log = logging.getLogger(__name__)

WINDOW_CHARS = 1200
STRIDE_CHARS = 600
MIN_CHARS = 800


def analyse(
    gateway: PrivacyGateway | None,
    texts: list[ArtifactText],
    *,
    weight: float = 0.25,
    scorer: LogprobScorer | None = None,
) -> SignalResult:
    result = SignalResult(kind=SignalKind.PERPLEXITY, weight=weight)

    if scorer is None:
        result.status = SignalStatus.UNAVAILABLE
        result.note = (
            "Перплексия требует локальной модели с logprobs "
            "(AI_LLM__PROVIDER=local). Сигнал не участвует, вес перераспределён."
        )
        return result

    skipped = [text.path for text in texts if text.partial]
    if skipped:
        result.note = "пропущены как доступные фрагментом: " + ", ".join(skipped[:6])

    scores: list[float] = []
    for artifact in texts:
        if artifact.partial or len(artifact.text) < MIN_CHARS:
            continue
        windows = _windows(artifact.text)
        try:
            nlls = [scorer.mean_nll(text) for _, _, text in windows]
        except (LLMError, LLMUnavailable) as exc:
            log.warning("перплексия недоступна: %s", exc)
            result.status = SignalStatus.FAILED
            result.note = f"локальная модель не ответила: {exc}"
            return result

        usable = [(w, nll) for w, nll in zip(windows, nlls, strict=False) if nll is not None]
        if len(usable) < 2:
            continue

        values = [nll for _, nll in usable]
        mean_nll = statistics.mean(values)
        burstiness = statistics.pstdev(values) / mean_nll if mean_nll else 1.0

        score = _combine(mean_nll, burstiness)
        if score < 0.4:
            continue

        scores.append(score)
        worst = min(usable, key=lambda item: item[1])
        (start, end, excerpt), _nll = worst
        result.spans.append(
            Span(
                artifact=artifact.path,
                start=start,
                end=end,
                start_line=artifact.text.count("\n", 0, start) + 1,
                end_line=artifact.text.count("\n", 0, end) + 1,
                score=score,
                signals=[SignalKind.PERPLEXITY],
                reason=(
                    f"равномерно низкая неожиданность текста "
                    f"(средняя NLL {mean_nll:.2f}, разброс {burstiness:.0%})"
                ),
                excerpt=excerpt[:200],
            )
        )
        result.findings.append(
            f"{artifact.path}: NLL {mean_nll:.2f}, разброс между окнами {burstiness:.0%}"
        )

    if not scores:
        result.score = 0.05
        result.findings.append("Аномально ровной перплексии не обнаружено.")
        return result

    result.score = round(max(scores), 3)
    return result


def _combine(mean_nll: float, burstiness: float) -> float:
    """Свести две меры в один скор.

    Пороги подобраны грубо и предназначены для калибровки на вердиктах
    ревьюеров: подтверждённые и отклонённые спаны копятся в базе, и именно
    они, а не наши догадки, должны в итоге задавать границы.
    """
    low_nll = max(0.0, min(1.0, (2.6 - mean_nll) / 1.6))
    flat = max(0.0, min(1.0, (0.45 - burstiness) / 0.35))
    return round(0.4 * low_nll + 0.6 * flat, 3)


def _windows(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    position = 0
    while position < len(text):
        end = min(position + WINDOW_CHARS, len(text))
        out.append((position, end, text[position:end]))
        if end == len(text):
            break
        position += STRIDE_CHARS
    return out


class LogprobScorer:
    """Обёртка над локальным completions-эндпоинтом с logprobs.

    Вынесена в отдельный класс, чтобы её можно было подменить в тестах и
    чтобы сигнал не зависел от конкретного сервинга: у vLLM и Ollama формат
    ответа отличается в мелочах.
    """

    def __init__(self, complete_with_logprobs) -> None:
        self._complete = complete_with_logprobs

    def mean_nll(self, text: str) -> float | None:
        logprobs = self._complete(text)
        if not logprobs:
            return None
        return -statistics.mean(logprobs)
