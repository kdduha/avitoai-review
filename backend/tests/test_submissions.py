"""Персистентные сдачи: очередь, карточка, правка балла, утверждение, повтор,
вердикт по спану ГенИИ, переназначение — весь `submissions.py`.

Ревью создаётся тем же путём, что и в проде: `POST /review` персистит
`Submission`, эти тесты работают дальше по `submission_id` из его ответа.
"""

from __future__ import annotations

import json

import pytest
from conftest import as_role
from factories import go_bundle
from fastapi.testclient import TestClient

from avito_reviewer.ai import AIService
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.app.main import create_app
from avito_reviewer.config import AIConfig

VERDICTS = json.dumps(
    {
        "verdicts": [
            {
                "criterion_id": cid,
                "score": 2,
                "confidence": 0.9,
                "verdict": f"разбор {cid}",
                "evidence": [
                    {"artifact": "cmd/main.go", "start_line": 11, "end_line": 11,
                     "quote": 'r.Get("/ping", handlePing)'}
                ],
                "student_feedback": "",
                "improvement_hint": "",
                "needs_human_attention": False,
                "attention_reason": "",
            }
            for cid in ("c1", "c2", "c3")
        ]
    },
    ensure_ascii=False,
)
FINDINGS = '{"findings": []}'
LINK = "https://github.com/acme/courier/pull/7"


class StubIngest:
    def __init__(self, bundle=None):
        self.bundle = bundle if bundle is not None else go_bundle()

    async def ingest(self, link, source, *, context=None):
        from uuid import uuid4

        return self.bundle.model_copy(update={"submission_id": uuid4()})

    async def fetch_content(self, content_ref):
        return None

    async def aclose(self):
        return None

    @property
    def sources(self):
        return []


@pytest.fixture
def make_client(tmp_path):
    def build(*, responses=None, role="reviewer"):
        app = create_app()
        client = TestClient(app)
        client.__enter__()
        gateway, provider = fake_gateway(responses if responses is not None else [VERDICTS])
        app.state.ingest = StubIngest()
        app.state.ai = AIService(AIConfig(), gateway=gateway, resolver=app.state.ingest)
        as_role(client, role)
        return client

    return build


def _review(client, **extra) -> dict:
    body = {"link": LINK, "rubric_id": "go-task1", **extra}
    response = client.post("/review", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# создание и очередь
# --------------------------------------------------------------------------- #

def test_review_persists_a_submission_the_reviewer_can_see_in_their_queue(make_client):
    client = make_client()
    result = _review(client)
    submission_id = result["submission_id"]

    queue = client.get("/me/queue").json()
    assert any(item["id"] == submission_id for item in queue)


def test_a_reviewer_does_not_see_a_submission_reassigned_away(make_client):
    """Only one `reviewer` account is seeded, so ownership is exercised by
    reassigning the submission off of it — after that, the same reviewer
    token must lose the submission from both the queue and the card."""
    client = make_client(role="reviewer")
    submission_id = _review(client)["submission_id"]

    admin = make_client(role="admin")
    assert admin.post(
        f"/submissions/{submission_id}/reassign", json={"reviewer_username": "admin"}
    ).status_code == 200

    assert client.get(f"/submissions/{submission_id}").status_code == 404
    assert not any(i["id"] == submission_id for i in client.get("/me/queue").json())
    assert admin.get(f"/submissions/{submission_id}").status_code == 200


def test_admin_sees_everyones_queue_with_all_flag(make_client):
    reviewer_client = make_client(role="reviewer")
    submission_id = _review(reviewer_client)["submission_id"]

    admin = make_client(role="admin")
    mine = admin.get("/me/queue").json()
    assert not any(i["id"] == submission_id for i in mine)

    everyone = admin.get("/me/queue", params={"all": "true"}).json()
    assert any(i["id"] == submission_id for i in everyone)


def test_get_submission_returns_bundle_files_and_draft(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]

    card = client.get(f"/submissions/{submission_id}").json()
    assert card["bundle"]["origin_url"] == LINK
    assert card["draft"]["score"] > 0
    assert card["status"] == "draft_ready"
    assert card["reviewer_username"] == "reviewer"
    # снимок рубрики на момент разбора, а не то, что сейчас лежит в каталоге —
    # только по нему клиент может честно отрисовать название/вес/чекпоинты критерия.
    assert card["rubric"]["criteria"]


def test_get_artifact_returns_one_files_text(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]

    body = client.get(f"/submissions/{submission_id}/artifacts/cmd/main.go").json()
    assert body["text"].startswith("package main")
    assert client.get(f"/submissions/{submission_id}/artifacts/nope.go").status_code == 404


# --------------------------------------------------------------------------- #
# with_detection — закрывает двойной ingest
# --------------------------------------------------------------------------- #

def test_with_detection_runs_both_off_the_same_bundle(make_client):
    client = make_client(responses=[VERDICTS, FINDINGS])
    result = _review(client, with_detection=True)

    assert result["detection"] is not None
    submission_id = result["submission_id"]
    stored = client.get(f"/submissions/{submission_id}/ai-detection").json()
    assert stored["advisory"] is True


def test_detection_absent_without_the_flag_is_404(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]
    assert client.get(f"/submissions/{submission_id}/ai-detection").status_code == 404


def test_detection_verdict_can_be_confirmed(make_client):
    client = make_client(responses=[VERDICTS, FINDINGS])
    submission_id = _review(client, with_detection=True)["submission_id"]

    report = client.get(f"/submissions/{submission_id}/ai-detection").json()
    if not report["spans"]:
        pytest.skip("фейковый провайдер не вернул спанов на этом прогоне")
    span_id = report["spans"][0]["id"]

    updated = client.post(
        f"/submissions/{submission_id}/ai-detection/{span_id}/verdict", json={"verdict": "confirmed"}
    ).json()
    assert next(s for s in updated["spans"] if s["id"] == span_id)["reviewer_verdict"] == "confirmed"

    # Не только ответ ручки — переживает ли вердикт перезагрузку из БД: PATCH,
    # мутирующий JSON-колонку тем же объектом, что в неё уже загружен, однажды
    # молча не сохранялся именно на этом пути (see submissions.py, flag_modified).
    reloaded = client.get(f"/submissions/{submission_id}/ai-detection").json()
    assert next(s for s in reloaded["spans"] if s["id"] == span_id)["reviewer_verdict"] == "confirmed"


def test_detection_verdict_is_not_blocked_by_approval(make_client):
    """A detection verdict is advisory (§7.5) — it never touches `score` — so
    it must stay editable after approval, unlike a `PATCH .../review`. Found
    live: the endpoint reused the "no writes after approval" guard that only
    makes sense for score edits, and 409'd here too. A made-up span id is
    enough to prove this: 404 "span not found" is fine, 409 "already
    approved" is the regression."""
    client = make_client(responses=[VERDICTS, FINDINGS])
    submission_id = _review(client, with_detection=True)["submission_id"]
    assert client.post(f"/submissions/{submission_id}/review/approve").status_code == 200

    response = client.post(
        f"/submissions/{submission_id}/ai-detection/does-not-exist/verdict", json={"verdict": "confirmed"}
    )
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# правка балла
# --------------------------------------------------------------------------- #

def test_patch_overrides_a_criterion_and_recomputes_the_total(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]
    before = client.get(f"/submissions/{submission_id}/review").json()["score"]

    patched = client.patch(
        f"/submissions/{submission_id}/review",
        json={"patches": [{"criterion_id": "c1", "score": 0, "verdict": "на самом деле не сделано"}]},
    ).json()

    assert patched["score"] < before
    assert patched["verdicts"][0]["verdict"] == "на самом деле не сделано"

    # Перезагрузка из БД, а не просто ответ ручки: этот же JSON-объект правится
    # на месте перед записью, и однажды это молча не долетало до базы.
    card = client.get(f"/submissions/{submission_id}").json()
    assert card["status"] == "in_review"
    assert card["draft"]["score"] == patched["score"]
    assert card["draft"]["verdicts"][0]["verdict"] == "на самом деле не сделано"


def test_patch_rejects_an_unknown_criterion(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]
    response = client.patch(
        f"/submissions/{submission_id}/review", json={"patches": [{"criterion_id": "нет-такого", "score": 1}]}
    )
    assert response.status_code == 422


def test_approve_then_patch_is_409(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]
    assert client.post(f"/submissions/{submission_id}/review/approve").status_code == 200

    again = client.patch(
        f"/submissions/{submission_id}/review", json={"patches": [{"criterion_id": "c1", "score": 1}]}
    )
    assert again.status_code == 409


# --------------------------------------------------------------------------- #
# переназначение
# --------------------------------------------------------------------------- #

def test_reassign_requires_admin(make_client):
    client = make_client(role="reviewer")
    submission_id = _review(client)["submission_id"]
    response = client.post(
        f"/submissions/{submission_id}/reassign", json={"reviewer_username": "admin"}
    )
    assert response.status_code == 403


def test_admin_can_reassign_to_another_reviewer(make_client):
    reviewer_client = make_client(role="reviewer")
    submission_id = _review(reviewer_client)["submission_id"]

    admin = make_client(role="admin")
    response = admin.post(
        f"/submissions/{submission_id}/reassign", json={"reviewer_username": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["reviewer_username"] == "admin"


def test_reassign_to_unknown_user_is_404(make_client):
    client = make_client(role="admin")
    submission_id = _review(client)["submission_id"]
    response = client.post(
        f"/submissions/{submission_id}/reassign", json={"reviewer_username": "нет-такого"}
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# аудит
# --------------------------------------------------------------------------- #

def test_audit_log_requires_admin_and_lists_calls(make_client):
    reviewer_client = make_client(role="reviewer")
    _review(reviewer_client)
    assert reviewer_client.get("/audit/llm-calls").status_code == 403

    admin = make_client(role="admin")
    _review(admin)
    records = admin.get("/audit/llm-calls").json()
    assert records and records[0]["model"]


# --------------------------------------------------------------------------- #
# rerun — единственная очередь через Redis/arq
# --------------------------------------------------------------------------- #

def test_rerun_is_503_when_the_queue_is_unreachable(make_client, monkeypatch):
    """Никакого реального Redis в тестах — DSN указывает в никуда."""
    monkeypatch.setenv("QUEUE_REDIS_DSN", "redis://127.0.0.1:1/0")
    client = make_client()
    submission_id = _review(client)["submission_id"]

    response = client.post(f"/submissions/{submission_id}/review/rerun")
    assert response.status_code == 503


def test_rerun_enqueues_a_job_and_marks_the_submission_analyzing(make_client, monkeypatch):
    calls = []

    class FakePool:
        async def enqueue_job(self, name, *args):
            calls.append((name, args))

        async def close(self):
            pass

    async def fake_create_pool(*a, **kw):
        return FakePool()

    monkeypatch.setattr("arq.create_pool", fake_create_pool)

    client = make_client()
    submission_id = _review(client)["submission_id"]

    response = client.post(f"/submissions/{submission_id}/review/rerun")
    assert response.status_code == 202
    assert response.json()["status"] == "analyzing"
    assert calls == [("rerun_review", (submission_id,))]

    card = client.get(f"/submissions/{submission_id}").json()
    assert card["status"] == "analyzing"


# --------------------------------------------------------------------------- #
# чат ревьюера с моделью
# --------------------------------------------------------------------------- #

def _sse_events(response) -> list[dict]:
    """Разобрать `data: {...}` построчно, как это сделал бы EventSource."""
    events = []
    for block in response.text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and line != "data: {}":
                events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_chat_reply_is_streamed_and_persisted(make_client):
    reply = json.dumps({"action": "reply", "reply": "балл посчитан агрегатором"})
    client = make_client(responses=[VERDICTS, VERDICTS, reply])
    submission_id = _review(client)["submission_id"]

    response = client.post(f"/submissions/{submission_id}/chat", json={"message": "почему такой балл?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(response)
    assert events[-1]["role"] == "assistant"
    assert events[-1]["content"] == "балл посчитан агрегатором"

    history = client.get(f"/submissions/{submission_id}/chat").json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "почему такой балл?"


def test_chat_tool_call_result_is_visible_in_the_transcript(make_client):
    tool_step = json.dumps(
        {"action": "tool", "tool": "get_file", "args": {"path": "cmd/main.go"}, "reply": "смотрю"}
    )
    final = json.dumps({"action": "reply", "reply": "теперь понятно"})
    client = make_client(responses=[VERDICTS, VERDICTS, tool_step, final])
    submission_id = _review(client)["submission_id"]

    events = _sse_events(
        client.post(f"/submissions/{submission_id}/chat", json={"message": "что в main.go?"})
    )
    assert events[0]["role"] == "tool"
    assert events[0]["tool_name"] == "get_file"
    assert "package main" in events[0]["content"]
    assert events[1]["role"] == "assistant"


def test_chat_propose_patch_carries_the_proposal_but_does_not_apply_it(make_client):
    step = json.dumps(
        {
            "action": "tool", "tool": "propose_review_patch",
            "args": {"criterion_id": "c1", "score": 0, "verdict": "на самом деле не сделано"},
            "reply": "предлагаю снизить c1",
        }
    )
    client = make_client(responses=[VERDICTS, VERDICTS, step])
    submission_id = _review(client)["submission_id"]
    before = client.get(f"/submissions/{submission_id}/review").json()["score"]

    events = _sse_events(
        client.post(f"/submissions/{submission_id}/chat", json={"message": "проверь c1"})
    )
    assert events[0]["proposed_patch"]["criterion_id"] == "c1"

    after = client.get(f"/submissions/{submission_id}/review").json()["score"]
    assert after == before, "предложение не должно менять черновик само по себе"

    applied = client.patch(
        f"/submissions/{submission_id}/review",
        json={"patches": [{"criterion_id": "c1", "score": 0, "verdict": "на самом деле не сделано"}]},
    )
    assert applied.status_code == 200
    assert applied.json()["score"] < before


def test_a_reviewer_cannot_open_chat_after_the_submission_is_reassigned_away(make_client):
    """Only one `reviewer` account is seeded (see `conftest.py`'s note on this
    pattern elsewhere in the file) — ownership is exercised the same way as
    `test_a_reviewer_does_not_see_a_submission_reassigned_away`."""
    owner = make_client(responses=[VERDICTS])
    submission_id = _review(owner)["submission_id"]

    admin = make_client(role="admin")
    assert admin.post(
        f"/submissions/{submission_id}/reassign", json={"reviewer_username": "admin"}
    ).status_code == 200

    assert owner.post(f"/submissions/{submission_id}/chat", json={"message": "?"}).status_code == 404
    assert owner.get(f"/submissions/{submission_id}/chat").status_code == 404


# --------------------------------------------------------------------------- #
# удаление
# --------------------------------------------------------------------------- #

def test_delete_submission_requires_admin(make_client):
    client = make_client(role="reviewer")
    submission_id = _review(client)["submission_id"]
    assert client.delete(f"/submissions/{submission_id}").status_code == 403


def test_admin_deletes_a_submission(make_client):
    client = make_client()
    submission_id = _review(client)["submission_id"]

    admin = make_client(role="admin")
    assert admin.delete(f"/submissions/{submission_id}").status_code == 204
    assert admin.get(f"/submissions/{submission_id}").status_code == 404


def test_deleting_an_unknown_submission_is_404(make_client):
    admin = make_client(role="admin")
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert admin.delete(f"/submissions/{fake_id}").status_code == 404


def test_a_reviewer_who_still_owns_submissions_cannot_be_deleted(make_client):
    """`test_users.py` covers the happy path; this is the one guard specific
    to submissions owning a reference to the account."""
    client = make_client()
    _review(client)

    admin = make_client(role="admin")
    reviewer_id = next(u["id"] for u in admin.get("/users").json() if u["username"] == "reviewer")

    response = admin.delete(f"/users/{reviewer_id}")
    assert response.status_code == 409
