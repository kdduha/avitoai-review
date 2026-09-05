"""Итеративный чат (§6.3): вызов тула, финальный ответ, предложенная правка.

`run_chat` — то, что дальше стримит роутер, тестируется здесь напрямую, без
HTTP и без SSE-обвязки: цикл детерминирован при фейковом провайдере с
заранее записанными ответами, ровно как батчи ревью в `test_review.py`.
"""

from __future__ import annotations

import json

from factories import atext, go_rubric

from avito_reviewer.ai.chat import run_chat
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.ai.review import CriterionVerdict, ReviewDraft

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
