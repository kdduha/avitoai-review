"""Слой доступа к моделям: обезличивание, маршрутизация, аудит, разбор ответа."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from avito_reviewer.ai.llm import (
    DataClass,
    FakeProvider,
    LLMError,
    LLMUnavailable,
    PrivacyGateway,
    RoutePolicy,
    Scrubber,
    StructuredError,
    TaskKind,
    complete_json,
    fake_gateway,
    provider_from_config,
    residual_risk,
)
from avito_reviewer.ai.llm.structured import extract_json
from avito_reviewer.config import LLMConfig


# --------------------------------------------------------------------------- #
# обезличивание
# --------------------------------------------------------------------------- #

def test_scrubber_replaces_contacts():
    result = Scrubber().scrub("Пишите на ivan.petrov@avito.ru или +7 916 123-45-67")
    assert "ivan.petrov@avito.ru" not in result.text
    assert "+7 916 123-45-67" not in result.text
    assert result.redactions == 2


def test_same_value_gets_the_same_token():
    """Связность важнее анонимности: одно значение — один токен."""
    result = Scrubber().scrub("автор ivan@x.ru, ревьюер ivan@x.ru, второй автор pete@x.ru")
    assert result.text.count("[EMAIL_1]") == 2
    assert "[EMAIL_2]" in result.text


def test_rehydrate_restores_original():
    scrubbed = Scrubber().scrub("почта ivan@x.ru")
    assert scrubbed.rehydrate(scrubbed.text) == "почта ivan@x.ru"


def test_residual_risk_catches_leftovers():
    assert residual_risk("контакт leftover@mail.ru")
    assert not residual_risk("контакт [EMAIL_1]")


# --------------------------------------------------------------------------- #
# шлюз
# --------------------------------------------------------------------------- #

def test_gateway_scrubs_before_sending():
    gateway, provider = fake_gateway(["ответ"])
    gateway.complete(
        [{"role": "user", "content": "студент ivan@x.ru сдал работу"}], task=TaskKind.REVIEW
    )
    assert "ivan@x.ru" not in provider.last_prompt
    assert "[EMAIL_1]" in provider.last_prompt


def test_gateway_rehydrates_the_answer():
    gateway, _ = fake_gateway(["связаться с [EMAIL_1]"])
    result = gateway.complete([{"role": "user", "content": "почта ivan@x.ru"}], task=TaskKind.REVIEW)
    assert result.text == "связаться с ivan@x.ru"


def test_ner_never_leaves_the_perimeter():
    """Отправлять персональные данные наружу, чтобы их найти, бессмысленно."""
    external = FakeProvider(responses=["внешний"], name="external", is_local=False)
    local = FakeProvider(responses=["локальный"], name="local", is_local=True)
    gateway = PrivacyGateway(external=external, local=local)

    result = gateway.complete([{"role": "user", "content": "текст"}], task=TaskKind.NER)
    assert result.route is RoutePolicy.LOCAL_ONLY
    assert result.text == "локальный"
    assert external.calls == []


def test_leftover_pd_downgrades_the_route(monkeypatch):
    """Fail-safe: сомнение решается в пользу локальной модели."""
    external = FakeProvider(responses=["внешний"], name="external", is_local=False)
    local = FakeProvider(responses=["локальный"], name="local", is_local=True)
    gateway = PrivacyGateway(external=external, local=local)

    # Скрабер не знает этот формат, валидатор остаточного риска — знает.
    import avito_reviewer.ai.llm.gateway as gateway_module
    from avito_reviewer.ai.llm.scrub import ScrubResult

    class LeakyScrubber(Scrubber):
        def scrub(self, text):  # type: ignore[override]
            return ScrubResult(text=text, mapping={}, redactions=0)

    monkeypatch.setattr(gateway_module, "Scrubber", LeakyScrubber)
    result = gateway.complete(
        [{"role": "user", "content": "почта leftover@mail.ru"}], task=TaskKind.REVIEW
    )

    assert result.downgraded is True
    assert result.route is RoutePolicy.LOCAL_ONLY
    assert external.calls == []


def test_force_local_disables_external_calls():
    external = FakeProvider(responses=["внешний"], name="external", is_local=False)
    local = FakeProvider(responses=["локальный"], name="local", is_local=True)
    gateway = PrivacyGateway(external=external, local=local, force_local=True)

    assert gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW).text == "локальный"
    assert external.calls == []


def test_local_only_without_local_provider_fails_loudly():
    gateway = PrivacyGateway(external=FakeProvider(name="external", is_local=False), local=None)
    with pytest.raises(LLMUnavailable, match="локальной модели"):
        gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.NER)


# --------------------------------------------------------------------------- #
# конфиг провайдера
# --------------------------------------------------------------------------- #

def test_default_provider_needs_no_key():
    """Сервис обязан подниматься и тесты обязаны идти без ключа."""
    assert isinstance(provider_from_config(LLMConfig()), FakeProvider)


def test_local_provider_is_marked_local():
    provider = provider_from_config(LLMConfig(provider="local"))
    assert provider.is_local is True


def test_openrouter_without_a_key_fails_at_startup_not_mid_run():
    with pytest.raises(LLMError, match="API_KEY"):
        provider_from_config(LLMConfig(provider="openrouter"))


# --------------------------------------------------------------------------- #
# аудит
# --------------------------------------------------------------------------- #

def test_audit_records_every_call_without_the_prompt():
    gateway, _ = fake_gateway(["ответ"])
    gateway.complete([{"role": "user", "content": "секрет ivan@x.ru"}], task=TaskKind.REVIEW)
    record = gateway.audit.records[0]
    assert record.redactions == 1
    assert len(record.prompt_sha256) == 64
    assert "ivan@x.ru" not in str(record.__dict__)


def test_audit_counts_cost():
    gateway, _ = fake_gateway(["a", "b"])
    for _ in range(2):
        gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW)
    summary = gateway.audit.summary()
    assert summary["calls"] == 2
    assert summary["cost_rub"] > 0


def test_checkpoint_scopes_the_summary_to_one_run():
    """Журнал общий на приложение, а счёт за прогон должен быть свой у каждого."""
    gateway, _ = fake_gateway(["a", "b", "c"])
    gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW)
    mark = gateway.audit.checkpoint()
    gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW)
    gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW)

    assert gateway.audit.summary(since=mark)["calls"] == 2
    assert gateway.audit.summary()["calls"] == 3


def test_audit_records_failures():
    provider = FakeProvider(responses=[LLMError("500")])
    gateway = PrivacyGateway(external=provider, local=provider)
    with pytest.raises(LLMError):
        gateway.complete([{"role": "user", "content": "x"}], task=TaskKind.REVIEW)
    assert gateway.audit.records[0].error


# --------------------------------------------------------------------------- #
# структурированный вывод
# --------------------------------------------------------------------------- #

class Answer(BaseModel):
    score: int
    comment: str


@pytest.mark.parametrize(
    "raw",
    [
        '{"score": 3, "comment": "ок"}',
        '```json\n{"score": 3, "comment": "ок"}\n```',
        'Вот результат:\n{"score": 3, "comment": "ок"}\nГотово.',
        '{"score": 3, "comment": "ок",}',
    ],
)
def test_json_survives_common_model_habits(raw):
    gateway, _ = fake_gateway([raw])
    answer, _ = complete_json(
        gateway, [{"role": "user", "content": "оцени"}], Answer, task=TaskKind.REVIEW
    )
    assert answer.score == 3


def test_broken_json_triggers_one_repair_attempt():
    gateway, provider = fake_gateway(["совсем не json", '{"score": 5, "comment": "ок"}'])
    answer, _ = complete_json(
        gateway, [{"role": "user", "content": "оцени"}], Answer, task=TaskKind.REVIEW
    )
    assert answer.score == 5
    assert len(provider.calls) == 2
    assert "не прошёл разбор" in provider.calls[1][-1]["content"]


def test_hopeless_output_raises_with_the_raw_text():
    gateway, _ = fake_gateway(["мусор", "снова мусор"])
    with pytest.raises(StructuredError) as exc:
        complete_json(gateway, [{"role": "user", "content": "оцени"}], Answer, task=TaskKind.REVIEW)
    assert exc.value.raw == "снова мусор"


def test_extract_json_prefers_the_outermost_object():
    assert extract_json('шум {"a": {"b": 1}} хвост') == '{"a": {"b": 1}}'


# --------------------------------------------------------------------------- #
# архитектурное правило
# --------------------------------------------------------------------------- #

SOURCE = Path(__file__).resolve().parents[1] / "src" / "avito_reviewer"

MODEL_SDKS = ("import openai", "from openai", "import anthropic", "from anthropic", "litellm")
RAW_NETWORK = ("import urllib.request", "import requests", "import httpx", "import socket")


def _modules_importing(needles: tuple[str, ...], *, allowed: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(SOURCE)}: {needle}"
        for path in SOURCE.rglob("*.py")
        if not set(path.relative_to(SOURCE).parts) & set(allowed)
        for needle in needles
        if needle in path.read_text(encoding="utf-8")
    ]


def test_llm_calls_leave_only_through_the_gateway():
    """Обращаться к моделям вправе только `ai/llm`.

    Это тот самый тест, который делает обещание «персональные данные не уходят
    мимо шлюза» проверяемым, а не декларативным. Сетевые вызовы в `ingest`
    правилом разрешены — доступ к источнику сдачи это его работа, — но SDK
    моделей запрещены и там.
    """
    assert not _modules_importing(MODEL_SDKS, allowed=("llm",)), (
        "SDK модели вне ai/llm: " + ", ".join(_modules_importing(MODEL_SDKS, allowed=("llm",)))
    )
    offenders = _modules_importing(RAW_NETWORK, allowed=("llm", "ingest"))
    assert not offenders, "сетевой клиент вне ai/llm и ingest: " + ", ".join(offenders)


def test_the_ai_layer_does_not_import_the_provider_stack():
    """Слою нужны модели ingest, а не его HTTP-клиент."""
    ai = SOURCE / "ai"
    offenders = [
        str(path.relative_to(ai))
        for path in ai.rglob("*.py")
        if "githubkit" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, "AI-слой знает о провайдере ingest: " + ", ".join(offenders)
