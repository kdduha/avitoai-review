"""PrivacyGateway — единственная точка выхода к моделям.

Ни один сервис не создаёт провайдера сам и не импортирует его. Всё, что
уходит наружу, проходит здесь: объявление класса данных, обезличивание,
проверка остаточного риска, выбор маршрута, вызов, регидратация, аудит.

Это архитектурное правило, а не рекомендация: в CI стоит проверка, что
`urllib`, `openai` и подобное не импортируются вне пакета `llm`. Именно она
превращает «мы не сливаем персональные данные» в проверяемое утверждение.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from avito_reviewer.config import LLMConfig

from .audit import AuditLog, AuditRecord
from .providers import (
    FakeProvider,
    LLMError,
    LLMResponse,
    LLMUnavailable,
    Provider,
    provider_from_config,
)
from .routing import DataClass, RoutePolicy, TaskKind, resolve_policy
from .scrub import Identity, Scrubber, residual_risk


@dataclass
class GatewayResult:
    text: str
    request_id: str
    model: str
    route: RoutePolicy
    tokens_in: int
    tokens_out: int
    redactions: int
    downgraded: bool = False
    truncated: bool = False


class PrivacyGateway:
    def __init__(
        self,
        external: Provider | None = None,
        local: Provider | None = None,
        *,
        audit: AuditLog | None = None,
        force_local: bool = False,
        task_models: dict[str, str] | None = None,
    ) -> None:
        """
        `force_local=True` отключает внешние вызовы целиком. Это режим для
        демонстрации полностью локального контура и аварийный тумблер, если
        служба безопасности запретит внешних провайдеров.
        """
        self.external = external
        self.local = local or (external if external and getattr(external, "is_local", False) else None)
        self.audit = audit or AuditLog()
        self.force_local = force_local
        self.task_models = task_models or {}
        """Матрица роутинга: какой задаче какая модель. Пусто — модель провайдера."""

    # ------------------------------------------------------------------ #

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        task: TaskKind,
        data_class: DataClass = DataClass.CONTAINS_PD,
        route: RoutePolicy | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        json_mode: bool = False,
        identities: Sequence[Identity] = (),
    ) -> GatewayResult:
        """`identities` — те, чья личность известна до разбора.

        Скрабер вычищает их точно, а не по совпадению шаблона: логин студента
        стоит в каждой строке импорта, и угадывать его было бы странно, когда
        он лежит в бандле.

        `route` — требование вызывающего, а не пожелание: `LOCAL_ONLY` наружу
        не уйдёт ни при каких настройках. Обратного действия у него нет —
        задачу из `FORCED_LOCAL` наружу им не вытолкнуть, и понижение по
        остаточному риску он не отменяет. Маршрут можно только ужесточить.
        """
        request_id = uuid.uuid4().hex[:12]
        resolved = resolve_policy(task, data_class)
        if route is RoutePolicy.LOCAL_ONLY:
            resolved = RoutePolicy.LOCAL_ONLY
        route = resolved
        downgraded = False

        scrubber = Scrubber(identities)
        scrubbed: list[dict[str, str]] = []
        redactions = 0
        mapping: dict[str, str] = {}

        for message in messages:
            result = scrubber.scrub(message["content"])
            redactions += result.redactions
            mapping.update(result.mapping)
            scrubbed.append({**message, "content": result.text})

        # Валидатор остаточного риска: если после скраба что-то осталось,
        # маршрут понижается принудительно. Fail-safe, а не fail-open.
        if route is RoutePolicy.EXTERNAL_AFTER_SCRUB:
            leftovers = residual_risk("\n".join(m["content"] for m in scrubbed), identities)
            if leftovers:
                route = RoutePolicy.LOCAL_ONLY
                downgraded = True

        if self.force_local:
            route = RoutePolicy.LOCAL_ONLY

        # Внешнего провайдера нет, локальный есть: считаем локально и говорим об
        # этом. Уронить задачу было бы строже, но не безопаснее — данные и так
        # не покидают периметр, — а `AI_LLM__PROVIDER=local` иначе не работал бы
        # вовсе: локальный контур целиком должен включаться одной переменной.
        if route is RoutePolicy.EXTERNAL_AFTER_SCRUB and self.external is None and self.local:
            route = RoutePolicy.LOCAL_ONLY
            downgraded = True

        provider = self._pick(route, task)
        started = time.monotonic()
        error: str | None = None

        try:
            response = provider.complete(
                scrubbed, temperature=temperature,
                max_tokens=max_tokens, json_mode=json_mode,
                model=self.task_models.get(task.value),
            )
        except (LLMError, LLMUnavailable) as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._record(request_id, provider, task, data_class, route, redactions,
                         scrubbed, None, int((time.monotonic() - started) * 1000), error)
            raise

        self._record(request_id, provider, task, data_class, route, redactions,
                     scrubbed, response, response.latency_ms, None)

        # Регидратация: настоящие значения возвращаются только внутрь периметра.
        text = response.text
        for token, original in mapping.items():
            text = text.replace(token, original)

        return GatewayResult(
            text=text,
            request_id=request_id,
            model=response.model,
            route=route,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            redactions=redactions,
            downgraded=downgraded,
            truncated=response.truncated,
        )

    # ------------------------------------------------------------------ #

    def _pick(self, route: RoutePolicy, task: TaskKind) -> Provider:
        if route is RoutePolicy.LOCAL_ONLY:
            if self.local is None:
                raise LLMUnavailable(
                    f"Задача {task.value} требует локальной модели, но локальный "
                    f"провайдер не настроен (AI_LLM__PROVIDER=local)"
                )
            return self.local
        if self.external is None:
            raise LLMUnavailable("Внешний провайдер не настроен")
        return self.external

    def _record(
        self, request_id: str, provider: Provider, task: TaskKind,
        data_class: DataClass, route: RoutePolicy, redactions: int,
        messages: list[dict[str, str]], response: LLMResponse | None,
        latency_ms: int, error: str | None,
    ) -> None:
        # Сырой промпт не сохраняется — только хэш и счётчики.
        prompt_hash = hashlib.sha256(
            json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

        self.audit.add(
            AuditRecord(
                request_id=request_id,
                provider=getattr(provider, "name", "unknown"),
                model=response.model if response else getattr(provider, "model", "unknown"),
                task=task.value,
                data_class=data_class.value,
                route=route.value,
                redactions=redactions,
                prompt_sha256=prompt_hash,
                tokens_in=response.tokens_in if response else 0,
                tokens_out=response.tokens_out if response else 0,
                latency_ms=latency_ms,
                reported_cost_rub=response.cost_rub if response else None,
                error=error,
            )
        )


def gateway_from_config(config: LLMConfig) -> PrivacyGateway:
    """One gateway per application: it owns the audit journal the run reports against."""
    provider = provider_from_config(config)
    is_local = getattr(provider, "is_local", False)
    return PrivacyGateway(
        external=None if is_local else provider,
        local=provider if is_local else None,
        force_local=config.force_local,
        task_models=dict(config.task_models),
    )


def fake_gateway(responses: list[str] | None = None) -> tuple[PrivacyGateway, FakeProvider]:
    """Шлюз на фейковом провайдере: тесты и демо без ключа."""
    provider = FakeProvider(responses=list(responses or []))
    return PrivacyGateway(external=provider, local=provider), provider
