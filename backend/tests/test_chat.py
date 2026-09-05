"""Итеративный чат (§6.3): вызов тула, финальный ответ, предложенная правка.

`run_chat` — то, что дальше стримит роутер, тестируется здесь напрямую, без
HTTP и без SSE-обвязки: цикл детерминирован при фейковом провайдере с
заранее записанными ответами, ровно как батчи ревью в `test_review.py`.
"""

from __future__ import annotations

import json

from factories import atext, go_rubric

from avito_reviewer.ai.chat import run_chat
from avito_reviewer.ai.detection import DetectionReport, SignalKind, SignalResult
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.ai.review import CriterionVerdict, Evidence, EvidenceStatus, ReviewDraft

RUBRIC = go_rubric()
DRAFT = ReviewDraft(
    assignment_id=RUBRIC.assignment_id,
    max_score=RUBRIC.scale.total_max,
    score=4,
    passed=True,
    verdicts=[
        CriterionVerdict(criterion_id="c1", score=2, verdict="структура на месте"),
        CriterionVerdict(criterion_id="c2", score=2, verdict="эндпоинты отвечают"),
    ],
)
TEXTS = [atext("cmd/main.go", text="package main\n\nfunc main() {}\n")]


def _run(response: str, *, message: str = "почему по c2 не максимум?"):
    gateway, provider = fake_gateway([response])
    steps = run_chat(
        gateway,
        rubric=RUBRIC,
        draft=DRAFT,
        texts=TEXTS,
        diffs={},
        history=[],
        message=message,
    )
    return steps, provider


def test_a_tool_call_is_executed_and_fed_back(monkeypatch):
    tool_step = json.dumps(
        {"action": "tool", "tool": "get_file", "args": {"path": "cmd/main.go"}, "reply": "смотрю файл"}
    )
    final_step = json.dumps({"action": "reply", "reply": "в файле пусто, поэтому балл ниже максимума"})
    gateway, provider = fake_gateway([tool_step, final_step])

    steps = run_chat(
        gateway, rubric=RUBRIC, draft=DRAFT, texts=TEXTS, diffs={}, history=[],
        message="почему не максимум?",
    )

    assert steps[0].kind == "tool" and steps[0].tool_name == "get_file"
    assert "package main" in steps[0].content
    assert steps[1].kind == "reply"
    assert len(provider.calls) == 2


def test_unknown_file_is_reported_not_crashed():
    tool_step = json.dumps(
        {"action": "tool", "tool": "get_file", "args": {"path": "нет-такого.go"}, "reply": "смотрю"}
    )
    steps, _ = _run(tool_step)
    assert "не входит в разбор" in steps[0].content


def test_propose_review_patch_stops_the_loop_and_carries_the_patch():
    step = json.dumps(
        {
            "action": "tool", "tool": "propose_review_patch",
            "args": {"criterion_id": "c2", "score": 6, "verdict": "на самом деле всё покрыто"},
            "reply": "предлагаю поднять c2 до максимума",
        }
    )
    steps, provider = _run(step)

    assert len(steps) == 1
    assert steps[0].kind == "tool" and steps[0].tool_name == "propose_review_patch"
    assert steps[0].proposed_patch is not None
    assert steps[0].proposed_patch.criterion_id == "c2"
    assert steps[0].proposed_patch.score == 6
    assert len(provider.calls) == 1, "после предложения патча цикл не должен звать модель снова"


def test_a_direct_reply_needs_no_tool():
    step = json.dumps({"action": "reply", "reply": "балл посчитан агрегатором, вот объяснение"})
    steps, _ = _run(step)
    assert steps == [steps[0]]
    assert steps[0].kind == "reply"


def test_malformed_model_output_becomes_a_readable_reply_not_a_crash():
    steps, _ = _run("это не json вовсе")
    assert steps[0].kind == "reply"
    assert steps[0].content


def test_too_many_tool_calls_stop_with_a_message_not_an_infinite_loop():
    tool_step = json.dumps(
        {"action": "tool", "tool": "get_criterion", "args": {"criterion_id": "c1"}, "reply": "смотрю"}
    )
    gateway, provider = fake_gateway([tool_step] * 10)
    steps = run_chat(
        gateway, rubric=RUBRIC, draft=DRAFT, texts=TEXTS, diffs={}, history=[],
        message="?", max_steps=3,
    )
    assert steps[-1].kind == "reply"
    assert len(provider.calls) == 3


def test_the_criterion_tool_shows_the_quotes_the_score_stands_on():
    """Спросив про критерий, спрашивают и про то, на чём стоит балл.

    Отдельного тула для цитат нет намеренно: он стоил бы лишнего шага цикла
    ради данных, которые уже лежат в том же черновике.
    """
    draft = ReviewDraft(
        assignment_id=RUBRIC.assignment_id,
        max_score=RUBRIC.scale.total_max,
        verdicts=[
            CriterionVerdict(
                criterion_id="c1",
                score=1,
                verdict="структура есть, тестов нет",
                evidence=[
                    Evidence(
                        artifact="cmd/main.go",
                        start_line=1,
                        quote="package main",
                        status=EvidenceStatus.VALID,
                    ),
                    Evidence(
                        artifact="cmd/main.go",
                        start_line=99,
                        quote="func TestPing",
                        status=EvidenceStatus.WRONG_LOCATION,
                    ),
                ],
            )
        ],
    )
    tool_step = json.dumps(
        {"action": "tool", "tool": "get_criterion", "args": {"criterion_id": "c1"}, "reply": "смотрю"}
    )
    gateway, _ = fake_gateway([tool_step, json.dumps({"action": "reply", "reply": "вот почему"})])

    steps = run_chat(
        gateway, rubric=RUBRIC, draft=draft, texts=TEXTS, diffs={}, history=[],
        message="почему по c1 не максимум?",
    )

    shown = steps[0].content
    assert "package main" in shown, "сошедшаяся цитата должна быть видна"
    assert "не сошлись" in shown, "несошедшаяся важнее сошедшейся — её и проверяет ревьюер"


def test_gate_facts_and_the_detection_summary_reach_the_context():
    """Гейт установил факты кодом — агент не должен переспрашивать их у файлов.

    Без этого он пересказывает по тексту то, что уже проверено, и иногда
    расходится с гейтом; ревьюер читает расхождение как ошибку разбора.
    """
    draft = ReviewDraft(
        assignment_id=RUBRIC.assignment_id,
        max_score=RUBRIC.scale.total_max,
        gate_facts=["в работе есть go.mod", "тесты найдены: 3 файла"],
        verdicts=[CriterionVerdict(criterion_id="c1", score=2, verdict="ок")],
    )
    detection = DetectionReport(
        label="слабые признаки",
        overall_score=0.31,
        signals=[SignalResult(kind=SignalKind.STYLOMETRY, weight=0.15)],
    )
    gateway, provider = fake_gateway([json.dumps({"action": "reply", "reply": "отвечаю"})])

    run_chat(
        gateway, rubric=RUBRIC, draft=draft, texts=TEXTS, diffs={}, history=[],
        message="что с работой?", detection=detection,
    )

    prompt = provider.last_prompt
    assert "тесты найдены: 3 файла" in prompt
    assert "слабые признаки" in prompt
    assert "решение принимает ревьюер" in prompt, "сигнал обязан приезжать подписанным"
