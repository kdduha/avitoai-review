"""Агрегатор баллов и оркестрация ревью.

Половина тестов — про сбои. Ревью прогоняется потоком, и «упало — покажем
ошибку» здесь не ответ: ревьюер должен получить всё, что удалось разобрать, и
видеть, чего не хватает.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from factories import go_bundle, go_rubric, partial_artifact, texts_of

from avito_reviewer.ai.llm import LLMUnavailable, fake_gateway
from avito_reviewer.ai.review import (
    CriterionVerdict,
    ReviewService,
    aggregate,
    explain,
)
from avito_reviewer.ai.rubric import LatePolicy, Scale
from avito_reviewer.config import ReviewOptions

VALID_QUOTES = {
    "c1": ("cmd/main.go", 10, "r := chi.NewRouter()"),
    "c2": ("cmd/main.go", 11, 'r.Get("/ping", handlePing)'),
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
                    if with_evidence
                    else []
                ),
                "student_feedback": "получилось аккуратно, дальше докрутим",
                "improvement_hint": "добавить тесты",
                "needs_human_attention": False,
                "attention_reason": "",
            }
        )
    return json.dumps({"verdicts": verdicts}, ensure_ascii=False)


def run(gateway, bundle=None, rubric=None, **kwargs):
    """Ревью тем же путём, что и в приложении: сначала тексты, потом разбор."""
    bundle = bundle or go_bundle()
    options = kwargs.pop("options", None)
    return ReviewService(gateway, options).review(
        texts_of(bundle),
        rubric or go_rubric(),
        submitted_at=bundle.submitted_at,
        deadline_at=bundle.deadline_at,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# агрегатор
# --------------------------------------------------------------------------- #

def test_score_is_summed_and_rounded_to_step():
    rubric = go_rubric(scale=Scale(total_max=6, pass_threshold=4, step=0.5))
    verdicts = [
        CriterionVerdict(criterion_id=cid, score=1.3, verdict="") for cid in ("c1", "c2", "c3")
    ]
    result = aggregate(verdicts, rubric)
    assert result.raw_score == pytest.approx(3.9)
    assert result.rounded_score == 4.0


def test_weights_are_applied():
    rubric = go_rubric()
    rubric.criteria[0].weight = 2.0
    assert aggregate([CriterionVerdict(criterion_id="c1", score=1.0, verdict="")], rubric).raw_score == 2.0


def test_failed_minimum_blocks_pass_despite_high_total():
    """В системном дизайне провал по обязательному критерию не компенсируется."""
    verdicts = [
        CriterionVerdict(criterion_id="c1", score=0.0, verdict=""),  # минимум 1
        CriterionVerdict(criterion_id="c2", score=2.0, verdict=""),
        CriterionVerdict(criterion_id="c3", score=2.0, verdict=""),
    ]
    result = aggregate(verdicts, go_rubric())
    assert result.final_score == 4.0
    assert result.passed is False
    assert "обязательный минимум" in result.pass_explanation


def test_without_a_threshold_there_is_no_verdict_at_all():
    """Порога нет в условии — «зачёт» выдумывать нельзя.

    Раньше здесь стояло `True`, и работа, обнулённая штрафом за просрочку,
    показывалась ревьюеру и студенту как «зачёт, 0 из 6».
    """
    rubric = go_rubric(scale=Scale(total_max=6, pass_threshold=None, step=0.5))
    bundle = go_bundle()
    result = aggregate(
        [CriterionVerdict(criterion_id=cid, score=2.0, verdict="") for cid in ("c1", "c2", "c3")],
        rubric,
        submitted_at=bundle.deadline_at + timedelta(days=2),
        deadline_at=bundle.deadline_at,
    )
    assert result.final_score == 0.0, "просрочка обнуляет — это правило рубрики"
    assert result.passed is None, "порога нет: ни зачёта, ни незачёта"
    assert "решение за ревьюером" in result.pass_explanation


def test_a_failed_minimum_still_decides_without_a_threshold():
    """Обязательный минимум — правило самой рубрики, оно работает без порога."""
    rubric = go_rubric(scale=Scale(total_max=6, pass_threshold=None, step=0.5))
    result = aggregate([CriterionVerdict(criterion_id="c1", score=0.0, verdict="")], rubric)
    assert result.passed is False


def test_late_penalty_applies_to_the_total_not_to_criteria():
    rubric = go_rubric(late_policy=LatePolicy(grace_days=1, penalty_per_grace_day=1))
    bundle = go_bundle()
    verdicts = [
        CriterionVerdict(criterion_id=cid, score=2.0, verdict="") for cid in ("c1", "c2", "c3")
    ]
    result = aggregate(
        verdicts,
        rubric,
        submitted_at=bundle.deadline_at + timedelta(hours=3),
        deadline_at=bundle.deadline_at,
    )
    assert result.rounded_score == 6.0
    assert result.final_score == 5.0
    assert "штраф" in result.late_explanation


def test_two_days_late_is_zero():
    bundle = go_bundle()
    result = aggregate(
        [CriterionVerdict(criterion_id="c1", score=2.0, verdict="")],
        go_rubric(),
        submitted_at=bundle.deadline_at + timedelta(days=2),
        deadline_at=bundle.deadline_at,
    )
    assert result.final_score == 0.0


def test_unknown_criterion_is_not_counted_but_is_visible():
    result = aggregate([CriterionVerdict(criterion_id="выдуманный", score=99, verdict="")], go_rubric())
    assert result.raw_score == 0.0
    assert result.contributions[0]["counted"] is False


def test_explain_shows_every_term():
    text = explain(aggregate([CriterionVerdict(criterion_id="c1", score=1.5, verdict="")], go_rubric()))
    assert "c1" in text and "сумма с весами" in text and "итог:" in text


# --------------------------------------------------------------------------- #
# сервис целиком
# --------------------------------------------------------------------------- #

def test_happy_path_produces_a_draft():
    gateway, provider = fake_gateway([batch_response(["c1", "c2", "c3"])])
    draft = run(gateway)

    assert len(draft.verdicts) == 3
    assert draft.score == 6.0
    assert draft.passed is True
    assert draft.evidence_coverage == 1.0
    assert draft.needs_human_attention is False
    assert len(_criteria_calls(provider)) == 1


def _criteria_calls(provider) -> list[list[dict[str, str]]]:
    """Только запросы на оценку критериев.

    После них идёт ещё один — итоговый отзыв; он не про батчи, и считать его
    здесь значило бы мерить не то, что тест обещает измерить.
    """
    return [call for call in provider.calls if "Оцени каждый" in call[-1]["content"]]


def test_criteria_are_batched():
    gateway, provider = fake_gateway([batch_response(["c1", "c2"]), batch_response(["c3"])])
    run(gateway, options=ReviewOptions(batch_size=2))
    assert len(_criteria_calls(provider)) == 2


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
    gateway, _ = fake_gateway([response] * 3)
    draft = run(gateway, options=ReviewOptions(batch_size=1))

    assert draft.needs_human_attention is True
    assert draft.verdict("c1").needs_human_attention is True
    assert draft.evidence_coverage == 0.0


def test_one_failed_batch_does_not_lose_the_rest():
    """Черновик на два критерия из трёх полезнее пустого экрана с ошибкой."""
    gateway, _ = fake_gateway([batch_response(["c1", "c2"]), "совсем не json", "и снова не json"])
    draft = run(gateway, options=ReviewOptions(batch_size=2))

    assert draft.verdict("c1").score == 2.0
    assert "c3" in draft.failed_criteria
    assert draft.verdict("c3").needs_human_attention is True
    assert draft.needs_human_attention is True


def test_provider_outage_yields_a_manual_draft():
    gateway, _ = fake_gateway([LLMUnavailable("сеть недоступна")] * 4)
    draft = run(gateway)

    assert len(draft.verdicts) == 3
    assert all(v.needs_human_attention for v in draft.verdicts)
    assert draft.score == 0.0
    assert set(draft.failed_criteria) == {"c1", "c2", "c3"}


def test_model_cannot_invent_criteria():
    response = json.dumps(
        {
            "verdicts": [
                {"criterion_id": "c1", "score": 2, "confidence": 0.9, "verdict": "ок",
                 "evidence": [{"artifact": "cmd/main.go", "start_line": 10,
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
    draft = run(gateway, options=ReviewOptions(batch_size=1))

    assert draft.verdict("c99") is None
    assert draft.score <= go_rubric().scale.total_max


def test_gate_facts_reach_the_model():
    gateway, provider = fake_gateway([batch_response(["c1", "c2", "c3"])])
    run(gateway, gate_facts=["Количество тест-кейсов: ожидалось 21, фактически 18."])
    # Не `last_prompt`: последним теперь идёт итоговый отзыв, а факты гейта
    # нужны там, где оценивают критерии.
    assert any("фактически 18" in call[-1]["content"] for call in _criteria_calls(provider))


def test_partial_files_are_named_in_the_draft():
    """Ревьюер должен знать, по каким файлам вывод модели заведомо неполон."""
    bundle = go_bundle(artifacts=[*go_bundle().artifacts, partial_artifact("internal/store/pg.go")])
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"])])
    draft = run(gateway, bundle=bundle)

    assert draft.partial_artifacts == ["internal/store/pg.go"]
    assert draft.needs_human_attention is True
    assert any("показаны не целиком" in reason for reason in draft.attention_reasons)


def test_cost_is_reported_per_review_not_per_process():
    """Журнал шлюза общий на приложение — иначе второй черновик покажет счёт первого."""
    # На прогон уходит два вызова: батч критериев и следом итоговый отзыв.
    # Пустой JSON на второй — валидное «резюме не собралось».
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"]), "{}"] * 2)
    first = run(gateway)
    second = run(gateway)

    assert first.tokens_in > 0 and first.cost_rub > 0
    assert second.tokens_in == first.tokens_in
    assert gateway.audit.summary()["tokens_in"] == first.tokens_in + second.tokens_in


def test_overlapping_reviews_report_their_own_cost():
    """`/review` уходит в поток, и шлюз с журналом — общий на приложение.

    Пока счёт брался срезом по длине журнала, первый прогон записывал себе
    токены второго. Проверяем на настоящем перекрытии, а не на последовательных
    вызовах: провайдер держит паузу, чтобы прогоны заведомо шли внахлёст.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    from avito_reviewer.ai.llm import PrivacyGateway
    from avito_reviewer.ai.llm.providers import LLMResponse

    spans: list[tuple[float, float]] = []

    class SlowProvider:
        name, model, is_local = "slow", "slow-model", True

        def complete(self, messages, *, temperature=0.0, max_tokens=2000, json_mode=False, model=None):
            started = time.monotonic()
            time.sleep(0.05)
            spans.append((started, time.monotonic()))
            return LLMResponse(
                text=batch_response(["c1", "c2", "c3"]),
                model=self.model,
                tokens_in=100,
                tokens_out=50,
            )

    gateway = PrivacyGateway(external=SlowProvider(), local=SlowProvider())

    with ThreadPoolExecutor(max_workers=2) as pool:
        drafts = [f.result() for f in [pool.submit(run, gateway) for _ in range(2)]]

    # Без реального перекрытия тест ничего не доказывает; отрезков четыре,
    # поэтому ищем любую перекрывшуюся пару, а не распаковываем ровно два.
    from itertools import combinations

    assert any(
        later_start < earlier_end
        for (_, earlier_end), (later_start, _) in combinations(sorted(spans), 2)
    ), "прогоны не пересеклись — проверка вырождена"

    # По два вызова на прогон: критерии и итоговый отзыв, по 100 токенов.
    assert [d.tokens_in for d in drafts] == [200, 200]
    assert gateway.audit.summary()["tokens_in"] == 400


# --------------------------------------------------------------------------- #
# итоговый отзыв
# --------------------------------------------------------------------------- #

SUMMARY = json.dumps(
    {
        "strengths": ["Структура разложена по golang-standards."],
        "improvements": ["Добавить тест на /healthcheck."],
        "encouragement": "Основа собрана крепко, до полного балла осталось немного.",
    },
    ensure_ascii=False,
)


def test_the_draft_carries_a_summary_in_words():
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"]), SUMMARY])
    draft = run(gateway)

    assert draft.summary is not None
    assert draft.summary.strengths and draft.summary.improvements
    assert "осталось немного" in draft.summary.encouragement


def test_the_summary_never_sees_the_work_itself():
    """Резюме пересказывает вердикты, а не работу.

    Это и есть гарантия от выдумки: соврать про код можно, только если его
    видишь. В запрос уходят названия критериев, баллы и тексты вердиктов —
    ни строки исходников.
    """
    gateway, provider = fake_gateway([batch_response(["c1", "c2", "c3"]), SUMMARY])
    run(gateway)

    summary_call = provider.calls[-1][-1]["content"]
    assert "разбор по c1" in summary_call, "вердикты в запрос попадают"
    assert "package main" not in summary_call
    assert "func " not in summary_call


def test_a_failed_summary_leaves_the_draft_without_one():
    """Пустое место честнее выдуманного абзаца — и дороже целого прогона."""
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"]), "не json вовсе"])
    draft = run(gateway)

    assert draft.summary is None
    assert len(draft.verdicts) == 3, "критерии уцелели: резюне последний шаг"
    assert draft.score == 6.0


def test_an_empty_summary_is_dropped_rather_than_shown_blank():
    gateway, _ = fake_gateway([batch_response(["c1", "c2", "c3"]), "{}"])
    assert run(gateway).summary is None
