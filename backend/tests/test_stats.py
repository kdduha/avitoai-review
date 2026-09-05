"""Статистика потока и задания + ревьюеры на потоке и раскладка работ.

Проверяется не CRUD, а два обещания:
1. считается только записанное — нет утверждённых, нет и среднего балла;
2. план распределения **доезжает до базы**, а не остаётся в ответе.
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
                "verdict": f"разбор {cid}",
                "evidence": [
                    {"artifact": "cmd/main.go", "start_line": 11, "end_line": 11,
                     "quote": 'r.Get("/ping", handlePing)'}
                ],
                "student_feedback": "", "improvement_hint": "",
                "needs_human_attention": False, "attention_reason": "",
            }
            for cid in ("c1", "c2", "c3")
        ]
    },
    ensure_ascii=False,
)
LINK = "https://github.com/acme/courier/pull/7"


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
    app = create_app()
    gateway, _ = fake_gateway([VERDICTS] * 20)

    def client_as(role: str) -> TestClient:
        client = TestClient(app)
        client.__enter__()
        app.state.ingest = StubIngest()
        app.state.ai = AIService(AIConfig(), gateway=gateway, resolver=app.state.ingest)
        as_role(client, role)
        return client

    admin = client_as("admin")
    course = admin.post("/courses", json={"key": "go", "title": "Go"}).json()
    stream = admin.post("/streams", json={"course_id": course["id"], "key": "a"}).json()
    assignment = admin.post(
        "/assignments",
        json={
            "stream_id": stream["id"],
            "rubric_key": "go-task1",
            "deadline_at": "2026-09-20T21:00:00+00:00",
        },
    ).json()
    admin.post(f"/streams/{stream['id']}/students", json={"usernames": ["student"]})

    return {"client_as": client_as, "admin": admin, "stream": stream, "assignment": assignment}


def _submit(world) -> str:
    student = world["client_as"]("student")
    return student.post(
        "/me/submissions",
        json={"assignment_id": world["assignment"]["id"], "link": LINK},
    ).json()["id"]


# --------------------------------------------------------------------------- #
# считается только записанное
# --------------------------------------------------------------------------- #

def test_an_empty_stream_reports_nothing_rather_than_zeroes(world):
    """Нет утверждённых — нет среднего балла.

    Ноль на этом месте читался бы как «все написали на ноль», и рядом с
    настоящими числами это худшее из возможных сообщений.
    """
    stats = world["admin"].get(f"/stats/streams/{world['stream']['id']}").json()
    assert stats["submissions"] == 0
    assert stats["average_score"] is None
    assert stats["pass_rate"] is None
    assert stats["students"] == 1


def test_a_submitted_but_unapproved_work_counts_as_awaiting_not_as_a_score(world):
    _submit(world)
    stats = world["admin"].get(f"/stats/streams/{world['stream']['id']}").json()

    assert stats["submissions"] == 1
    assert stats["awaiting"] == 1
    assert stats["approved"] == 0
    assert stats["unassigned"] == 1, "студент сдал, ревьюера ещё не назначили"
    assert stats["average_score"] is None


def test_the_score_appears_only_after_a_human_approved_it(world):
    submission_id = _submit(world)
    admin = world["admin"]
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "reviewer"})
    world["client_as"]("reviewer").post(f"/submissions/{submission_id}/review/approve")

    stats = admin.get(f"/stats/streams/{world['stream']['id']}").json()
    assert stats["approved"] == 1
    assert stats["average_score"] is not None
    assert stats["pass_rate"] is not None
    assert sum(b["count"] for b in stats["by_assignment"][0]["histogram"]) == 1


def test_a_reviewer_may_read_the_statistics_of_their_stream(world):
    """Прятать от ревьюера результат его же работы незачем."""
    reviewer = world["client_as"]("reviewer")
    assert reviewer.get(f"/stats/streams/{world['stream']['id']}").status_code == 200
    assert (
        reviewer.get(f"/stats/assignments/{world['assignment']['id']}").status_code == 200
    )


def test_a_student_cannot_read_stream_statistics(world):
    student = world["client_as"]("student")
    assert student.get(f"/stats/streams/{world['stream']['id']}").status_code == 403


# --------------------------------------------------------------------------- #
# ревьюеры на потоке
# --------------------------------------------------------------------------- #

def test_a_student_is_not_assignable_as_a_reviewer(world):
    response = world["admin"].post(
        f"/streams/{world['stream']['id']}/reviewers", json={"usernames": ["student"]}
    )
    assert response.status_code == 422


def test_assigning_a_reviewer_twice_does_not_duplicate_the_link(world):
    admin, stream_id = world["admin"], world["stream"]["id"]
    admin.post(f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer"]})
    rows = admin.post(
        f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer"]}
    ).json()
    assert len(rows) == 1
    assert rows[0]["roster_id"] is None, "карточки каталога для этого логина нет — и это видно"


def test_removing_a_reviewer_from_a_stream_keeps_the_work_they_already_hold(world):
    """Снять с потока — «не давать новых», а не «отобрать начатое»."""
    admin, stream_id = world["admin"], world["stream"]["id"]
    admin.post(f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer"]})
    submission_id = _submit(world)
    admin.post(f"/streams/{stream_id}/distribute")

    assert admin.delete(f"/streams/{stream_id}/reviewers/reviewer").status_code == 204
    card = admin.get(f"/submissions/{submission_id}").json()
    assert card["reviewer_username"] == "reviewer"


# --------------------------------------------------------------------------- #
# план доезжает до базы
# --------------------------------------------------------------------------- #

def test_distribution_writes_the_reviewer_onto_the_submission(world):
    admin, stream_id = world["admin"], world["stream"]["id"]
    admin.post(f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer"]})
    submission_id = _submit(world)

    result = admin.post(f"/streams/{stream_id}/distribute").json()
    assert result == {"assigned": 1, "unassigned": 0, "reasons": []}

    # Главное: работа видна в очереди ревьюера, а не только в ответе солвера.
    queue = world["client_as"]("reviewer").get("/me/queue").json()
    assert any(item["id"] == submission_id for item in queue)


def test_distribution_without_reviewers_refuses_instead_of_silently_doing_nothing(world):
    _submit(world)
    response = world["admin"].post(f"/streams/{world['stream']['id']}/distribute")
    assert response.status_code == 409


def test_already_assigned_work_is_not_reshuffled(world):
    """Ревьюер мог начать разбор — молча отобрать работу хуже, чем перекос."""
    admin, stream_id = world["admin"], world["stream"]["id"]
    admin.post("/users", json={"username": "second", "password": "avito2026", "role": "reviewer"})
    admin.post(f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer", "second"]})

    submission_id = _submit(world)
    admin.post(f"/submissions/{submission_id}/reassign", json={"reviewer_username": "second"})

    result = admin.post(f"/streams/{stream_id}/distribute").json()
    assert result["assigned"] == 0, "нераспределённых работ не осталось"

    card = admin.get(f"/submissions/{submission_id}").json()
    assert card["reviewer_username"] == "second"


def test_the_stream_stats_show_the_load_per_reviewer(world):
    admin, stream_id = world["admin"], world["stream"]["id"]
    admin.post(f"/streams/{stream_id}/reviewers", json={"usernames": ["reviewer"]})
    _submit(world)
    admin.post(f"/streams/{stream_id}/distribute")

    stats = admin.get(f"/stats/streams/{stream_id}").json()
    row = next(r for r in stats["by_reviewer"] if r["username"] == "reviewer")
    assert row["assigned"] == 1
    assert row["awaiting"] == 1
    assert row["approved"] == 0
    assert stats["unassigned"] == 0


def test_an_account_that_is_not_on_the_stream_is_not_in_the_load_table(world):
    admin, stream_id = world["admin"], world["stream"]["id"]
    _submit(world)
    admin.post(f"/submissions/{_submit(world)}/reassign", json={"reviewer_username": "reviewer"})

    stats = admin.get(f"/stats/streams/{stream_id}").json()
    assert stats["by_reviewer"] == [], "нагрузку показываем по назначенным на поток"
    assert stats["submissions"] == 2


def test_unknown_login_is_reported_by_name(world):
    response = world["admin"].post(
        f"/streams/{world['stream']['id']}/reviewers", json={"usernames": ["reviewer", "нет-такого"]}
    )
    assert response.status_code == 404
    assert "нет-такого" in response.json()["detail"]


def test_only_the_head_changes_who_reviews_the_stream(world):
    reviewer = world["client_as"]("reviewer")
    assert (
        reviewer.post(
            f"/streams/{world['stream']['id']}/reviewers", json={"usernames": ["reviewer"]}
        ).status_code
        == 403
    )
    assert reviewer.post(f"/streams/{world['stream']['id']}/distribute").status_code == 403


def test_a_second_student_login_does_not_leak_into_the_stream_numbers(world):
    """Сдачи считаются по заданиям потока, а не по всем строкам таблицы."""
    admin = world["admin"]
    admin.post("/users", json={"username": "petrov", "password": "avito2026", "role": "student"})
    other = TestClient(admin.app)
    other.__enter__()
    other.headers["Authorization"] = f"Bearer {login(other, 'petrov')}"

    # Не зачислен на поток — сдать не может, и в числах потока его нет.
    assert (
        other.post(
            "/me/submissions",
            json={"assignment_id": world["assignment"]["id"], "link": LINK},
        ).status_code
        == 403
    )
    stats = admin.get(f"/stats/streams/{world['stream']['id']}").json()
    assert stats["submissions"] == 0
