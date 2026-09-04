"""Классы данных и матрица маршрутизации.

Каждый вызов модели обязан объявить, что он несёт и куда это можно отправить.
Значения по умолчанию намеренно строгие: забыть указать класс данных должно
быть безопасно, а не удобно.
"""

from __future__ import annotations

from enum import Enum


class TaskKind(str, Enum):
    REVIEW = "review"          # разбор работы по критериям
    COMPILE = "compile"        # условие задания → черновик рубрики
    JUDGE = "judge"            # классификация фрагментов на признаки генерации
    CHAT = "chat"              # диалог ревьюера с моделью
    NER = "ner"                # поиск ПДн
    PERPLEXITY = "perplexity"  # logprobs для детектора
    EMBED = "embed"


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONTAINS_PD = "contains_pd"


class RoutePolicy(str, Enum):
    LOCAL_ONLY = "local_only"
    EXTERNAL_AFTER_SCRUB = "external_after_scrub"


# Задачи, которые не покидают периметр ни при каких настройках.
#
# NER ищет персональные данные — отправлять их наружу, чтобы найти, абсурдно.
# Перплексия требует logprobs, которых внешние провайдеры почти не отдают,
# и прогоняет слишком большой объём токенов, чтобы платить за него.
FORCED_LOCAL: frozenset[TaskKind] = frozenset(
    {TaskKind.NER, TaskKind.PERPLEXITY, TaskKind.EMBED}
)


def resolve_policy(task: TaskKind, data_class: DataClass) -> RoutePolicy:
    """Куда можно отправить этот вызов."""
    if task in FORCED_LOCAL:
        return RoutePolicy.LOCAL_ONLY
    if data_class is DataClass.CONTAINS_PD:
        return RoutePolicy.EXTERNAL_AFTER_SCRUB
    return RoutePolicy.EXTERNAL_AFTER_SCRUB
