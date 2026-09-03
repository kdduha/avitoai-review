"""Провайдеры моделей.

Локальный сервинг (vLLM, Ollama) и OpenRouter говорят на одном
OpenAI-совместимом протоколе, поэтому клиент один, а различаются они только
`base_url` и ключом. Это не экономия кода, а свойство архитектуры:
переключение всего контура на локальные модели — одна переменная окружения,
и его можно показать на демо, не трогая код.

Сеть через `urllib` из стандартной библиотеки. Лишняя зависимость в модуле,
который ходит наружу с чужими данными, — это лишняя поверхность, за которой
надо следить.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMUnavailable(LLMError):
    """Провайдер недоступен: сеть, ключ, лимиты. Конвейер должен пережить это."""


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str
    is_local: bool

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------- #

@dataclass
class OpenAICompatibleProvider:
    """Один клиент на оба маршрута.

    `is_local=True` означает, что запросы не покидают периметр, и шлюз может
    пропустить сюда данные, которые наружу отдавать нельзя.
    """

    base_url: str
    model: str
    api_key: str | None = None
    name: str = "openai-compatible"
    is_local: bool = False
    timeout: int = 120
    max_retries: int = 2

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = self.base_url.rstrip("/") + "/chat/completions"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                request = urllib.request.Request(
                    url, data=json.dumps(payload).encode("utf-8"),
                    headers=headers, method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "ignore")[:400]
                last_error = LLMError(f"{exc.code} от {self.name}: {detail}")
                # 4xx кроме 429 не лечится повтором
                if exc.code not in (408, 429) and exc.code < 500:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = LLMUnavailable(f"{self.name} недоступен: {exc}")
            except json.JSONDecodeError as exc:
                last_error = LLMError(f"{self.name} вернул не JSON: {exc}")
            else:
                usage = body.get("usage", {})
                return LLMResponse(
                    text=body["choices"][0]["message"]["content"] or "",
                    model=body.get("model", self.model),
                    tokens_in=usage.get("prompt_tokens", 0),
                    tokens_out=usage.get("completion_tokens", 0),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    raw=body,
                )

            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))

        raise last_error or LLMUnavailable(f"{self.name}: неизвестная ошибка")


# --------------------------------------------------------------------------- #

@dataclass
class FakeProvider:
    """Провайдер для тестов и демо без ключа.

    Отдаёт заранее подготовленные ответы по очереди. Нужен не столько для
    экономии, сколько чтобы тесты проверяли нашу логику — сборку промпта,
    валидацию цитат, арифметику — а не поведение чужой модели.
    """

    responses: list[str] = field(default_factory=list)
    name: str = "fake"
    model: str = "fake-model"
    is_local: bool = True
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    default: str = "{}"

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.calls.append(messages)
        text = self.responses.pop(0) if self.responses else self.default
        if isinstance(text, Exception):  # позволяет проверять обработку сбоев
            raise text
        return LLMResponse(text=text, model=self.model, tokens_in=100, tokens_out=50)

    @property
    def last_prompt(self) -> str:
        return "\n".join(m["content"] for m in self.calls[-1]) if self.calls else ""


# --------------------------------------------------------------------------- #

def provider_from_env() -> Provider:
    """Собрать провайдера по переменным окружения.

    AVITOAI_PROVIDER: local | openrouter | fake
    """
    kind = os.getenv("AVITOAI_PROVIDER", "fake").lower()

    if kind == "local":
        return OpenAICompatibleProvider(
            base_url=os.getenv("AVITOAI_LOCAL_BASE_URL", "http://localhost:8000/v1"),
            model=os.getenv("AVITOAI_MODEL", "qwen2.5-7b-instruct"),
            api_key=os.getenv("AVITOAI_API_KEY"),
            name="local",
            is_local=True,
        )

    if kind == "openrouter":
        key = os.getenv("AVITOAI_API_KEY")
        if not key:
            raise LLMError("AVITOAI_PROVIDER=openrouter, но AVITOAI_API_KEY не задан")
        return OpenAICompatibleProvider(
            base_url=os.getenv("AVITOAI_BASE_URL", "https://openrouter.ai/api/v1"),
            model=os.getenv("AVITOAI_MODEL", "openai/gpt-4o-mini"),
            api_key=key,
            name="openrouter",
            is_local=False,
        )

    return FakeProvider()
