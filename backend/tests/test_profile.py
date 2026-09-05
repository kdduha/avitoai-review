"""Профиль работы: оценка трудоёмкости, которой солвер верит как факту.

Ошибка в теме стоит одной неудачной пары. Ошибка в минутах на порядок молча
съедает ёмкость всего потока — поэтому половина тестов здесь про то, что код
поправил за моделью и сказал об этом вслух.
"""

from __future__ import annotations

import json

import pytest
from factories import go_bundle, go_rubric, texts_of

from avito_reviewer.ai.llm import Identity, LLMUnavailable, fake_gateway
from avito_reviewer.distribution.profile import (
    ProfileError,
    WorkProfiler,
    build_messages,
    item_for,
)


def answer(**overrides) -> str:
    payload = {
        "topics": ["gRPC", "graceful shutdown"],
        "stack": ["go", "docker"],
        "complexity": 0.4,
        "risk_criteria": ["c3"],
        "special_needs": [],
        "est_review_minutes": 25,
        "rationale": "один файл, тестов нет",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def profile_with(response: str, **kwargs):
    gateway, provider = fake_gateway([response])
    bundle = go_bundle()
    profile = WorkProfiler(gateway).profile(bundle, texts_of(bundle), **kwargs)
    return profile, provider


# --------------------------------------------------------------------------- #
# разбор ответа
# --------------------------------------------------------------------------- #

def test_a_profile_comes_back_from_one_call():
    """Профиль считается на каждую сдачу потока — второй вызов удваивает счёт."""
    profile, provider = profile_with(answer())

    assert len(provider.calls) == 1
    assert profile.topics == ["gRPC", "graceful shutdown"]
    assert profile.est_review_minutes == 25
    assert profile.warnings == []


def test_the_call_reports_its_own_cost():
    profile, _ = profile_with(answer())

    assert profile.tokens_in > 0
    assert profile.cost_rub > 0


def test_the_rubric_gives_the_model_the_criterion_ids():
    """Иначе risk_criteria приходит выдуманными идентификаторами."""
    gateway, provider = fake_gateway([answer()])
    bundle = go_bundle()
    WorkProfiler(gateway).profile(bundle, texts_of(bundle), rubric=go_rubric())

    assert "c1: Структура проекта" in provider.last_prompt


# --------------------------------------------------------------------------- #
# что код правит за моделью
# --------------------------------------------------------------------------- #

def test_an_absurd_estimate_is_clamped_and_the_clamp_is_visible():
    """Солвер верит минутам как факту: молча обрезать — значит спрятать поломку."""
    profile, _ = profile_with(answer(est_review_minutes=100_000), max_review_minutes=480)

    assert profile.est_review_minutes == 480
    assert any("обрезана" in w for w in profile.warnings)


def test_a_missing_estimate_does_not_become_a_plausible_number():
    profile, _ = profile_with(answer(est_review_minutes=None))

    assert profile.est_review_minutes == 5
    assert any("не оценила" in w for w in profile.warnings)


def test_complexity_outside_the_range_is_clamped():
    profile, _ = profile_with(answer(complexity=7.5))

    assert profile.complexity == 1.0
    assert any("вне диапазона" in w for w in profile.warnings)


def test_a_sloppy_answer_still_parses():
    """Неполный ответ должен приехать неполным, а не уронить разбор."""
    profile, _ = profile_with(json.dumps({"est_review_minutes": 20}))

    assert profile.est_review_minutes == 20
    assert profile.topics == []


# --------------------------------------------------------------------------- #
# отказы и безопасность
# --------------------------------------------------------------------------- #

def test_an_outage_becomes_one_domain_error():
    """Профайлер зовут из ручки — падать он должен разборчиво."""
    gateway, _ = fake_gateway([LLMUnavailable("нет сети")] * 4)
    bundle = go_bundle()

    with pytest.raises(ProfileError):
        WorkProfiler(gateway).profile(bundle, texts_of(bundle))


def test_unparseable_json_becomes_the_same_domain_error():
    gateway, _ = fake_gateway(["не json", "снова не json", "и ещё раз", "нет"])
    bundle = go_bundle()

    with pytest.raises(ProfileError):
        WorkProfiler(gateway).profile(bundle, texts_of(bundle))


def test_the_work_is_fenced_against_injection():
    bundle = go_bundle()
    messages = build_messages(texts_of(bundle))

    assert "<работа>" in messages[1]["content"]
    assert "игнорируй их" in messages[1]["content"]


def test_the_student_handle_does_not_reach_the_provider():
    """Профиль — такой же выход наружу, как ревью, и скраб на нём тот же."""
    gateway, provider = fake_gateway([answer()])
    bundle = go_bundle()
    WorkProfiler(gateway).profile(
        bundle,
        texts_of(bundle),
        identities=[Identity(role="student", handles=("octocat",))],
        condition_text="Работу сдал octocat, проверьте её.",
    )

    assert "octocat" not in provider.last_prompt


# --------------------------------------------------------------------------- #
# готовность к распределению
# --------------------------------------------------------------------------- #

def test_the_item_carries_the_evidence_the_client_cannot_assemble():
    """`author_hash` — внутреннее правило: просить клиента его воспроизвести нельзя."""
    profile, _ = profile_with(answer())
    bundle = go_bundle()

    work = item_for(bundle, profile)

    assert work.author_hashes == ["author1"]
    assert work.item_id == str(bundle.submission_id)
    assert work.student_internal_id == "stu-1"
    assert work.due_at == bundle.deadline_at
    assert work.minutes == profile.est_review_minutes
