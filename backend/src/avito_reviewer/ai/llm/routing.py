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
    PROFILE = "profile"        # что за работа и во сколько обойдётся разбор
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
    """Куда можно отправить этот вызов.

    Класс данных маршрут не меняет, и это не упущение. Персональные данные
    защищает не ярлык, а безусловный скраб на каждом вызове и принудительное
    понижение маршрута, когда после скраба что-то осталось (`gateway.complete`).
    `CONTAINS_PD` означает «обезличить и отправить», а не «не отправлять»: на
    этом стоит вся §8.2, иначе ревью работ было бы невозможно в принципе.

    Ярлык при этом не декоративен — он пишется в журнал аудита, и по нему
    видно, какого класса данные уходили наружу. А запретить конкретному вызову
    выходить наружу можно явно: `complete(..., route=RoutePolicy.LOCAL_ONLY)`.
    """
    if task in FORCED_LOCAL:
        return RoutePolicy.LOCAL_ONLY
    return RoutePolicy.EXTERNAL_AFTER_SCRUB
