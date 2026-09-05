"""Кабинет студента: свои задания, сдача по ссылке, свои оценки.

Главное правило проверяется первым: **до утверждения балла нет**. Пока
ревьюер не подтвердил разбор, студент видит «на проверке» — показать ему
предварительное число значило бы объявить оценку, которую поставила модель, а
не человек.
"""

from __future__ import annotations

import json

import pytest
from conftest import as_role, login
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
                "criterion_id": cid, "score": 2, "confidence": 0.9,
                "verdict": f"рабочая формулировка {cid}",
                "evidence": [
                    {"artifact": "cmd/main.go", "start_line": 11, "end_line": 11,
                     "quote": 'r.Get("/ping", handlePing)'}
                ],
                "student_feedback": f"понятное объяснение {cid}",
                "improvement_hint": f"докрутить {cid}",
                "needs_human_attention": False, "attention_reason": "",
            }
            for cid in ("c1", "c2", "c3")
        ]
    },
    ensure_ascii=False,
)
LINK = "https://github.com/acme/courier/pull/7"
SUMMARY = json.dumps(
    {
        "strengths": ["Структура читается."],
        "improvements": ["Добавить тест на /healthcheck."],
        "encouragement": "Хорошая основа, докрутить осталось немного.",
    },
    ensure_ascii=False,
)


class StubIngest:
    def __init__(self):
        self.bundle = go_bundle()

    async def ingest(self, link, source, *, context=None):
        from uuid import uuid4

        update = {"submission_id": uuid4()}
        if context is not None and context.deadline_at is not None:
            update["deadline_at"] = context.deadline_at
        return self.bundle.model_copy(update=update)

    async def fetch_content(self, content_ref):
        return None

    async def aclose(self):
        return None

    @property
    def sources(self):
        return []


@pytest.fixture
def world(tmp_path):
    """Один app на тест: методист заводит поток и задание, студент зачислен.

    Клиенты разных ролей смотрят в одну базу — иначе «ревьюер утвердил, студент
    увидел» не проверить.
    """
    app = create_app()
    # На разбор уходит два вызова: критерии и следом итоговый отзыв.
    gateway, _ = fake_gateway([VERDICTS, SUMMARY] * 8)

    def client_as(role: str) -> TestClient:
        client = TestClient(app)
        client.__enter__()
        app.state.ingest = StubIngest()
        app.state.ai = AIService(AIConfig(), gateway=gateway, resolver=app.state.ingest)
        as_role(client, role)
        return client

    admin = client_as("admin")
    course = admin.post("/courses", json={"key": "go", "title": "Go"}).json()
    stream = admin.post(
        "/streams", json={"course_id": course["id"], "key": "a", "title": "Осень"}
    ).json()
    assignment = admin.post(
        "/assignments",
        json={
            "stream_id": stream["id"],
            "rubric_key": "go-task1",
            "description": "Сдаём pull request",
            "deadline_at": "2026-09-20T21:00:00+00:00",
        },
    ).json()
    admin.post(f"/streams/{stream['id']}/students", json={"usernames": ["student"]})

    return {
        "client_as": client_as,
        "admin": admin,
        "assignment": assignment,
        "stream": stream,
    }


def _student(world) -> TestClient:
    return world["client_as"]("student")


# --------------------------------------------------------------------------- #
# что сдавать
# --------------------------------------------------------------------------- #

def test_a_student_sees_the_assignments_of_their_own_streams(world):
    student = _student(world)
    items = student.get("/me/assignments").json()
    assert len(items) == 1
    assert items[0]["course_key"] == "go"
    assert items[0]["description"] == "Сдаём pull request"
    assert items[0]["best_score"] is None, "утверждённых сдач ещё нет"


def test_an_unenrolled_account_sees_an_empty_list_not_an_error(world):
    """Заведён, но не добавлен в поток — штатное состояние, а не сбой."""
    admin = world["admin"]
    admin.post(
        "/users", json={"username": "petrov", "password": "avito2026", "role": "student"}
    )
    other = TestClient(admin.app)
    other.__enter__()
    other.headers["Authorization"] = f"Bearer {login(other, 'petrov')}"
    assert other.get("/me/assignments").json() == []


# --------------------------------------------------------------------------- #
# сдача
# --------------------------------------------------------------------------- #

def test_submitting_leaves_the_work_unassigned_for_a_reviewer(world):
    student = _student(world)
    response = student.post(
        "/me/submissions",
        json={"assignment_id": world["assignment"]["id"], "link": LINK},
    )
    assert response.status_code == 201, response.text

    # В очереди руководителя работа видна, ревьюера у неё нет: раздаёт
    # распределение, а не порядок прихода.
    queue = world["admin"].get("/me/queue?all=true").json()
    mine = [item for item in queue if item["id"] == response.json()["id"]]
    assert mine and mine[0]["reviewer_username"] is None


def test_a_student_cannot_submit_to_a_stream_they_are_not_on(world):
    admin = world["admin"]
    admin.post(
        "/users", json={"username": "sidorov", "password": "avito2026", "role": "student"}
    )
    other = TestClient(admin.app)
    other.__enter__()
    other.headers["Authorization"] = f"Bearer {login(other, 'sidorov')}"

    response = other.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    )
    assert response.status_code == 403


def test_the_deadline_of_the_assignment_reaches_the_submission(world):
    student = _student(world)
    card = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()
    assert card["deadline_at"].startswith("2026-09-20T21:00")


# --------------------------------------------------------------------------- #
# оценка появляется только после человека
# --------------------------------------------------------------------------- #

def test_before_approval_there_is_no_score_at_all(world):
    student = _student(world)
    card = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()

    assert card["approved"] is False
    assert card["score"] is None, "балл поставила модель, а не человек — показывать нельзя"
    assert card["passed"] is None
    assert card["verdicts"] == [], "разбор до утверждения студенту не показывают"


def test_after_approval_the_student_sees_the_score_and_the_feedback(world):
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]

    admin = world["admin"]
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "reviewer"})
    reviewer = world["client_as"]("reviewer")
    assert reviewer.post(f"/submissions/{submission_id}/review/approve").status_code == 200

    card = student.get(f"/me/submissions/{submission_id}").json()
    assert card["approved"] is True
    assert card["score"] is not None
    assert card["verdicts"], "после утверждения разбор становится обратной связью"


def test_the_student_reads_the_supportive_wording_not_the_working_one(world):
    """`student_feedback` писался для студента, `verdict` — для ревьюера."""
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]
    admin = world["admin"]
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "reviewer"})
    world["client_as"]("reviewer").post(f"/submissions/{submission_id}/review/approve")

    card = student.get(f"/me/submissions/{submission_id}").json()
    texts = [v["feedback"] for v in card["verdicts"]]
    assert any("понятное объяснение" in t for t in texts)
    assert not any("рабочая формулировка" in t for t in texts)


def test_the_raw_card_with_quotes_is_not_reachable_by_a_student(world):
    """Цитаты, уверенность и пометки «нужен человек» — кухня проверки."""
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]

    assert student.get(f"/submissions/{submission_id}").status_code == 403


def test_a_student_does_not_see_someone_elses_work(world):
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]

    admin = world["admin"]
    admin.post(
        "/users", json={"username": "ivanov", "password": "avito2026", "role": "student"}
    )
    other = TestClient(admin.app)
    other.__enter__()
    other.headers["Authorization"] = f"Bearer {login(other, 'ivanov')}"

    # 404, а не 403: существование чужой работы — тоже сведение о ней.
    assert other.get(f"/me/submissions/{submission_id}").status_code == 404
    assert other.get("/me/submissions").json() == []


def test_the_best_approved_score_lands_on_the_assignment(world):
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]

    assert student.get("/me/assignments").json()[0]["best_score"] is None

    admin = world["admin"]
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "reviewer"})
    world["client_as"]("reviewer").post(f"/submissions/{submission_id}/review/approve")

    item = student.get("/me/assignments").json()[0]
    assert item["submissions"] == 1
    assert item["best_score"] is not None


def test_the_summary_reaches_the_student_only_after_approval(world):
    """Отзыв словами — часть оценки, а не отдельная от неё сущность.

    До утверждения его нет по той же причине, по которой нет балла: разбор
    ещё не принят человеком.
    """
    student = _student(world)
    submission_id = student.post(
        "/me/submissions", json={"assignment_id": world["assignment"]["id"], "link": LINK}
    ).json()["id"]

    assert student.get(f"/me/submissions/{submission_id}").json()["summary"] is None

    admin = world["admin"]
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "reviewer"})
    world["client_as"]("reviewer").post(f"/submissions/{submission_id}/review/approve")

    summary = student.get(f"/me/submissions/{submission_id}").json()["summary"]
    assert summary["strengths"] and summary["improvements"]
    assert "докрутить" in summary["encouragement"]
