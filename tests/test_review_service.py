"""Тесты агрегатора и оркестрации ревью."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from doubles import Criterion, LatePolicy, Scale, go_bundle, go_rubric
from llm import fake_gateway
from review_service import CriterionVerdict, ReviewConfig, ReviewService, aggregate, explain
from review_service.schema import Evidence


VALID_QUOTES = {
    "c1": ("cmd/main.go", 9, 'r := chi.NewRouter()'),
    "c2": ("cmd/main.go", 10, 'r.Get("/ping", handlePing)'),
    "c3": ("cmd/main.go", 16, 'log.Println("Shutting down service-courier")'),
}


def batch_response(ids, *, score=2.0, confidence=0.9, with_evidence=True):
    verdicts = []
    for cid in ids:
        artifact, line, quote = VALID_QUOTES[cid]
        verdicts.append(
            {
                "criterion_id": cid,
                "score": score,
                "confidence": confidence,
                "verdict": f"разбор по {cid}",
                "evidence": (
                    [{"artifact": artifact, "start_line": line, "end_line": line, "quote": quote}]
                    if with_evidence else []
                ),
                "student_feedback": "получилось аккуратно, дальше докрутим",
                "improvement_hint": "добавить тесты",
                "needs_human_attention": False,
                "attention_reason": "",
            }
        )
    return json.dumps({"verdicts": verdicts}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# агрегатор
# --------------------------------------------------------------------------- #

def test_score_is_summed_and_rounded_to_step():
    rubric = go_rubric(scale=Scale(total_max=6, pass_threshold=4, step=0.5))
    verdicts = [
        CriterionVerdict(criterion_id="c1", score=1.3, verdict=""),
        CriterionVerdict(criterion_id="c2", score=1.3, verdict=""),
        CriterionVerdict(criterion_id="c3", score=1.3, verdict=""),
    ]
    result = aggregate(verdicts, rubric)
    assert result.raw_score == pytest.approx(3.9)
    assert result.rounded_score == 4.0


def test_weights_are_applied():
    rubric = go_rubric()
    rubric.criteria[0].weight = 2.0
    verdicts = [CriterionVerdict(criterion_id="c1", score=1.0, verdict="")]
    assert aggregate(verdicts, rubric).raw_score == 2.0


def test_failed_minimum_blocks_pass_despite_high_total():
    """В системном дизайне провал по обязательному критерию не компенсируется."""
    rubric = go_rubric()
    verdicts = [
        CriterionVerdict(criterion_id="c1", score=0.0, verdict=""),  # минимум 1
        CriterionVerdict(criterion_id="c2", score=2.0, verdict=""),
        CriterionVerdict(criterion_id="c3", score=2.0, verdict=""),
    ]
    result = aggregate(verdicts, rubric)
    assert result.final_score == 4.0
    assert result.passed is False
    assert "обязательный минимум" in result.pass_explanation


def test_late_penalty_applies_to_the_total_not_to_criteria():
    rubric = go_rubric(late_policy=LatePolicy(grace_days=1, penalty_per_grace_day=1))
    bundle = go_bundle()
    late = bundle.deadline_at + timedelta(hours=3)
    verdicts = [
        CriterionVerdict(criterion_id="c1", score=2.0, verdict=""),
        CriterionVerdict(criterion_id="c2", score=2.0, verdict=""),
        CriterionVerdict(criterion_id="c3", score=2.0, verdict=""),
    ]
    result = aggregate(verdicts, rubric, submitted_at=late, deadline_at=bundle.deadline_at)
    assert result.rounded_score == 6.0
    assert result.final_score == 5.0
    assert "штраф" in result.late_explanation


def test_two_days_late_is_zero():
    rubric = go_rubric()
    bundle = go_bundle()
    verdicts = [CriterionVerdict(criterion_id="c1", score=2.0, verdict="")]
    result = aggregate(
        verdicts, rubric,
        submitted_at=bundle.deadline_at + timedelta(days=2),
        deadline_at=bundle.deadline_at,
    )
    assert result.final_score == 0.0


def test_unknown_criterion_is_not_counted_but_is_visible():
    rubric = go_rubric()
    verdicts = [CriterionVerdict(criterion_id="выдуманный", score=99, verdict="")]
    result = aggregate(verdicts, rubric)
    assert result.raw_score == 0.0
    assert result.contributions[0]["counted"] is False


def test_explain_shows_every_term():
    rubric = go_rubric()
    verdicts = [CriterionVerdict(criterion_id="c1", score=1.5, verdict="")]
    text = explain(aggregate(verdicts, rubric))
    assert "c1" in text and "сумма с весами" in text and "итог:" in text


# --------------------------------------------------------------------------- #
# сервис целиком
# --------------------------------------------------------------------------- #

def test_happy_path_produces_a_draft():
    gateway, provider = fake_gateway([batch_response(["c1", "c2", "c3"])])
    draft = ReviewService(gateway).review(go_bundle(), go_rubric())

    assert len(draft.verdicts) == 3
    assert draft.score == 6.0
    assert draft.passed is True
    assert draft.evidence_coverage == 1.0
    assert draft.needs_human_attention is False
    assert len(provider.calls) == 1


def test_criteria_are_batched():
    gateway, provider = fake_gateway(
        [batch_response(["c1", "c2"]), batch_response(["c3"])]
    )
    ReviewService(gateway, ReviewConfig(batch_size=2)).review(go_bundle(), go_rubric())
    assert len(provider.calls) == 2


def test_fabricated_evidence_flags_the_draft():
    response = json.dumps(
        {
            "verdicts": [
                {
                    "criterion_id": "c1", "score": 2, "confidence": 0.95,
                    "verdict": "структура отличная",
                    "evidence": [
                        {"artifact": "cmd/main.go", "start_line": 3,
                         "quote": "здесь подключён контейнер зависимостей через wire"}
                    ],
                    "student_feedback": "", "improvement_hint": "",
                    "needs_human_attention": False, "attention_reason": "",
                }
            ]
        },
        ensure_ascii=False,
    )
    gateway, _ = fake_gateway([response, response, response])
    draft = ReviewService(gateway, ReviewConfig(batch_size=1)).review(go_bundle(), go_rubric())

    assert draft.needs_human_attention is True
    assert draft.verdict("c1").needs_human_attention is True
    assert draft.evidence_coverage == 0.0


def test_one_failed_batch_does_not_lose_the_rest():
    """Черновик на два критерия из трёх полезнее пустого экрана с ошибкой."""
    gateway, _ = fake_gateway([batch_response(["c1", "c2"]), "совсем не json", "и снова не json"])
    draft = ReviewService(gateway, ReviewConfig(batch_size=2)).review(go_bundle(), go_rubric())

    assert draft.verdict("c1").score == 2.0
    assert "c3" in draft.failed_criteria
    assert draft.verdict("c3").needs_human_attention is True
    assert draft.needs_human_attention is True


def test_provider_outage_yields_a_manual_draft():
    from llm.providers import LLMUnavailable

    gateway, _ = fake_gateway([LLMUnavailable("сеть недоступна")] * 4)
    draft = ReviewService(gateway).review(go_bundle(), go_rubric())

    assert len(draft.verdicts) == 3
    assert all(v.needs_human_attention for v in draft.verdicts)
    assert draft.score == 0.0
    assert set(draft.failed_criteria) == {"c1", "c2", "c3"}


def test_model_cannot_invent_criteria():
    response = json.dumps(
        {
            "verdicts": [
                {"criterion_id": "c1", "score": 2, "confidence": 0.9, "verdict": "ок",
                 "evidence": [{"artifact": "cmd/main.go", "start_line": 9,
                               "quote": "r := chi.NewRouter()"}],
                 "student_feedback": "", "improvement_hint": "",
                 "needs_human_attention": False, "attention_reason": ""},
                {"criterion_id": "c99", "score": 5, "confidence": 0.9,
                 "verdict": "бонус за старание", "evidence": [],
                 "student_feedback": "", "improvement_hint": "",
                 "needs_human_attention": False, "attention_reason": ""},
            ]
        },
        ensure_ascii=False,
    )
    gateway, _ = fake_gateway([response, batch_response(["c2"]), batch_response(["c3"])])
    draft = ReviewService(gateway, ReviewConfig(batch_size=1)).review(go_bundle(), go_rubric())

    assert draft.verdict("c99") is None
    assert draft.score <= go_rubric().scale.total_max


def test_gate_facts_reach_the_model():
    gateway, provider = fake_gateway([batch_response(["c1", "c2", "c3"])])
    ReviewService(gateway).review(
        go_bundle(), go_rubric(),
        gate_facts=["Количество тест-кейсов: ожидалось 21, фактически 18."],
    )
    assert "фактически 18" in provider.last_prompt


def test_cost_is_reported():
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"])])
    draft = ReviewService(gateway).review(go_bundle(), go_rubric())
    assert draft.tokens_in > 0
    assert draft.cost_rub > 0
