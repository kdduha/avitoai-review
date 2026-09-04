"""Структурированный ответ с восстановлением после сбоя разбора.

Модель регулярно возвращает JSON, обёрнутый в ```json, с висящей запятой или
с пояснением до и после. Ронять из-за этого обработку всего потока работ
нельзя, поэтому здесь три уровня: аккуратное извлечение, один ремонтный
запрос к модели с текстом ошибки, и только потом отказ.

Валидация по pydantic-модели, а не по свободному словарю: контракт вывода
должен быть один и тот же в коде, в тестах и в промпте.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .gateway import GatewayResult, PrivacyGateway
from .routing import DataClass, TaskKind
from .scrub import Identity

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class StructuredError(RuntimeError):
    """Модель так и не вернула валидный ответ по схеме."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def extract_json(text: str) -> str:
    """Достать JSON из ответа, что бы модель вокруг него ни написала."""
    text = text.strip()

    # Только ограда вокруг всего ответа. Искать ``` где угодно нельзя: работа
    # по системному дизайну состоит из блоков ```mermaid, модель их цитирует,
    # и тройные кавычки оказываются внутри значения JSON. Поиск по всему тексту
    # вырезал бы содержимое диаграммы вместо ответа.
    fenced = FENCE.fullmatch(text)
    if fenced:
        text = fenced.group(1).strip()

    # Модель любит предварять объект фразой «Вот результат:».
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            return text[start : end + 1]

    return text


def parse_json(text: str) -> object:
    # Сначала как есть: валидный ответ нельзя портить попытками его починить.
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    cleaned = extract_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Висящая запятая — самая частая поломка, и она чинится без модели.
        repaired = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(repaired)


def complete_json(
    gateway: PrivacyGateway,
    messages: list[dict[str, str]],
    model_cls: type[T],
    *,
    task: TaskKind,
    data_class: DataClass = DataClass.CONTAINS_PD,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    repair_attempts: int = 1,
    identities: Sequence[Identity] = (),
) -> tuple[T, GatewayResult]:
    """Получить ответ, разобранный в `model_cls`."""
    conversation = list(messages)
    last_raw = ""
    last_error = ""
    budget = max_tokens

    for attempt in range(repair_attempts + 1):
        result = gateway.complete(
            conversation,
            task=task,
            data_class=data_class,
            temperature=temperature,
            max_tokens=budget,
            json_mode=True,
            identities=identities,
        )
        last_raw = result.text

        try:
            payload = parse_json(result.text)
            return model_cls.model_validate(payload), result
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            last_error = _describe(exc)
            if attempt >= repair_attempts:
                break

            if result.truncated or not result.text.strip():
                # Модель не ошиблась в форматировании — ей не хватило места.
                # Пустой ответ у рассуждающей модели того же происхождения:
                # бюджет ушёл в `reasoning`, до содержимого очередь не дошла, и
                # `finish_reason` при этом бывает штатным. Просить «верни
                # валидный JSON» в обоих случаях бессмысленно — следующий ответ
                # упрётся в тот же потолок и удвоит счёт. Даём бюджет.
                log.warning(
                    "ответ %s при лимите %d токенов, повтор с %d",
                    "оборван" if result.truncated else "пуст",
                    budget,
                    budget * 2,
                )
                budget *= 2
                continue

            # Ремонтный запрос: показываем модели её собственный вывод и ошибку.
            conversation = conversation + [
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": (
                        "Ответ не прошёл разбор по схеме.\n"
                        f"Ошибка: {last_error}\n\n"
                        "Верни только валидный JSON по той же схеме, без пояснений "
                        "и без markdown-обрамления."
                    ),
                },
            ]

    raise StructuredError(
        f"Модель не вернула валидный ответ по схеме {model_cls.__name__}: {last_error}",
        raw=last_raw,
    )


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        problems = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()[:5]
        ]
        return "; ".join(problems)
    return str(exc)
