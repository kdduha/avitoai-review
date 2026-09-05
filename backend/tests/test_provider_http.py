"""Провайдер против настоящего HTTP.

Фейковый провайдер проверяет нашу логику, но не проверяет сам сетевой клиент:
заголовки, разбор ответа, поведение на 429 и 500, таймауты. Поднимаем
маленький сервер, отвечающий как OpenAI-совместимый эндпоинт, и проверяем
клиент против него. Ключей и сети наружу не требуется.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from avito_reviewer.ai.llm.providers import LLMError, LLMUnavailable, OpenAICompatibleProvider


class Handler(BaseHTTPRequestHandler):
    script: ClassVar[list] = []
    received: ClassVar[list] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        Handler.received.append({"path": self.path, "body": body, "headers": dict(self.headers)})

        status, payload = Handler.script.pop(0) if Handler.script else (200, _ok("готово"))
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):  # тишина в выводе тестов
        return


def _ok(text: str) -> dict:
    return {
        "model": "test-model",
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 7},
    }


@pytest.fixture
def server():
    Handler.script = []
    Handler.received = []
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def provider_for(server, **kwargs) -> OpenAICompatibleProvider:
    host, port = server.server_address
    return OpenAICompatibleProvider(
        base_url=f"http://{host}:{port}/v1",
        model="test-model",
        api_key="secret-key",
        max_retries=kwargs.pop("max_retries", 2),
        **kwargs,
    )


# --------------------------------------------------------------------------- #

def test_request_shape_and_auth_header(server):
    Handler.script = [(200, _ok("привет"))]
    response = provider_for(server).complete(
        [{"role": "user", "content": "как дела"}], temperature=0.2, max_tokens=99, json_mode=True
    )

    assert response.text == "привет"
    assert response.tokens_in == 42 and response.tokens_out == 7
    assert response.model == "test-model"

    sent = Handler.received[0]
    assert sent["path"].endswith("/chat/completions")
    assert sent["headers"]["Authorization"] == "Bearer secret-key"
    assert sent["body"]["temperature"] == 0.2
    assert sent["body"]["max_tokens"] == 99
    assert sent["body"]["response_format"] == {"type": "json_object"}


def test_server_error_is_retried(server):
    Handler.script = [(500, {"error": "boom"}), (200, _ok("со второго раза"))]
    response = provider_for(server).complete([{"role": "user", "content": "x"}])
    assert response.text == "со второго раза"
    assert len(Handler.received) == 2


def test_rate_limit_is_retried(server):
    Handler.script = [(429, {"error": "slow down"}), (200, _ok("ок"))]
    assert provider_for(server).complete([{"role": "user", "content": "x"}]).text == "ок"


def test_bad_request_is_not_retried(server):
    """Повторять 400 бессмысленно: ответ не изменится, а лимиты израсходуются."""
    Handler.script = [(400, {"error": "плохой запрос"})]
    with pytest.raises(LLMError, match="400"):
        provider_for(server).complete([{"role": "user", "content": "x"}])
    assert len(Handler.received) == 1


def test_unreachable_host_is_unavailable_not_error():
    """Разница важна: недоступность лечится повтором позже, ошибка запроса — нет."""
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1/v1", model="m", max_retries=0, timeout=1
    )
    with pytest.raises(LLMUnavailable):
        provider.complete([{"role": "user", "content": "x"}])


def test_local_provider_needs_no_key(server):
    Handler.script = [(200, _ok("локально"))]
    host, port = server.server_address
    provider = OpenAICompatibleProvider(
        base_url=f"http://{host}:{port}/v1", model="local-model", is_local=True
    )
    assert provider.complete([{"role": "user", "content": "x"}]).text == "локально"
    assert "Authorization" not in Handler.received[0]["headers"]


def test_gateway_works_over_real_http(server):
    """Сквозная проверка: обезличивание, отправка, регидратация."""
    from avito_reviewer.ai.llm import PrivacyGateway, TaskKind

    Handler.script = [(200, _ok("свяжитесь с [EMAIL_1]"))]
    provider = provider_for(server)
    gateway = PrivacyGateway(external=provider, local=provider)

    result = gateway.complete(
        [{"role": "user", "content": "автор ivan@avito.ru"}], task=TaskKind.REVIEW
    )

    assert "ivan@avito.ru" not in json.dumps(Handler.received[0]["body"], ensure_ascii=False)
    assert result.text == "свяжитесь с ivan@avito.ru"
    assert gateway.audit.records[0].redactions == 1


# --------------------------------------------------------------------------- #
# ответы неожиданной формы
# --------------------------------------------------------------------------- #

def test_null_usage_does_not_crash_the_request(server):
    """Шлюзы присылают `"usage": null`, и `.get("usage", {})` отдаёт None.

    Дальше падал AttributeError, которого конвейер не ловит: он ждёт LLMError.
    Один странный ответ шлюза ронял весь `/review` пятисоткой.
    """
    Handler.script = [(200, {"model": "m", "usage": None,
                             "choices": [{"message": {"content": "готово"}}]})]
    response = provider_for(server).complete([{"role": "user", "content": "x"}])

    assert response.text == "готово"
    assert response.tokens_in == 0 and response.cost_rub is None


@pytest.mark.parametrize(
    "body",
    [
        {"model": "m"},                                  # без choices
        {"model": "m", "choices": []},                   # пустой список
        {"model": "m", "choices": "нет"},                # вообще не список
        {"model": "m", "choices": [{"finish_reason": "stop"}]},  # без message
    ],
)
def test_malformed_body_becomes_a_catchable_error(server, body):
    """Неизвестная форма ответа — потеря одного батча, а не пятисотка на запрос."""
    Handler.script = [(200, body)]
    provider = provider_for(server, max_retries=0)

    if body.get("choices") == [{"finish_reason": "stop"}]:
        # `message` нет — это пустой ответ, его чинит повтор с большим бюджетом.
        assert provider.complete([{"role": "user", "content": "x"}]).text == ""
        return

    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "x"}])
