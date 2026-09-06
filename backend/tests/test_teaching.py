"""Курсы, потоки, задания: что настраивает методист и что из этого следует.

Главное здесь — не CRUD, а шов: **срок принадлежит заданию, а не сдаче**.
Пока дедлайн вводил ревьюер в форме проверки, опечатка в дате давала штраф за
просрочку там, где просрочки не было, и объяснить такой балл было нечем.
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
DEADLINE = "2026-09-01T18:00:00+00:00"


class StubIngest:
    def __init__(self):
        self.bundle = go_bundle()

    async def ingest(self, link, source, *, context=None):
        from uuid import uuid4

        # Дедлайн приезжает в бандл из контекста ingest — ровно так же, как в
        # проде: провайдер его не знает, он приходит сверху.
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
def app_client(tmp_path):
    def build(*, responses=None, role="methodist"):
        app = create_app()
        client = TestClient(app)
        client.__enter__()
        gateway, _ = fake_gateway(responses if responses is not None else [VERDICTS])
        app.state.ingest = StubIngest()
        app.state.ai = AIService(AIConfig(), gateway=gateway, resolver=app.state.ingest)
        as_role(client, role)
        return client

    return build


def _course_and_stream(client) -> str:
    course = client.post("/courses", json={"key": "go", "title": "Разработка на Go"})
    assert course.status_code == 201, course.text
    stream = client.post(
        "/streams", json={"course_id": course.json()["id"], "key": "a", "title": "Осень 2026"}
    )
    assert stream.status_code == 201, stream.text
    return stream.json()["id"]


def _assignment(client, stream_id, **extra) -> dict:
    body = {"stream_id": stream_id, "rubric_key": "go-task1", **extra}
    response = client.post("/assignments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# права
# --------------------------------------------------------------------------- #

def test_a_reviewer_reads_the_catalogue_but_does_not_change_it(app_client):
    """Ревьюер выбирает задание, значит должен его видеть. Менять срок — нет.

    Правка дедлайна задним числом молча меняет штраф за просрочку на всех
    сданных работах потока: это решение методиста, а не того, кто держит
    открытой одну работу.
    """
    methodist = app_client(role="methodist")
    stream_id = _course_and_stream(methodist)
    _assignment(methodist, stream_id, deadline_at=DEADLINE)

    reviewer = app_client(role="reviewer")
    assert reviewer.get("/courses").status_code == 200
    assert len(reviewer.get("/assignments").json()) == 1

    denied = reviewer.post("/courses", json={"key": "qa", "title": "Tech QA"})
    assert denied.status_code == 403


def test_a_methodist_can_still_grade(app_client):
    """Лестница прав: методист — надстройка над ревьюером, а не соседняя роль.

    Человек, написавший рубрику, разбирает спорную работу по ней сам.
    """
    methodist = app_client(role="methodist")
    assert methodist.get("/me/queue").status_code == 200


# --------------------------------------------------------------------------- #
# срок принадлежит заданию
# --------------------------------------------------------------------------- #

def test_the_deadline_comes_from_the_assignment_not_from_the_form(app_client):
    client = app_client(responses=[VERDICTS, VERDICTS], role="methodist")
    stream_id = _course_and_stream(client)
    assignment = _assignment(client, stream_id, deadline_at=DEADLINE)

    response = client.post("/review", json={"link": LINK, "assignment_id": assignment["id"]})
    assert response.status_code == 200, response.text

    # Проверяем бандл, а не карточку: именно этот срок доезжает до агрегатора
    # и решает, будет ли штраф за просрочку.
    assert response.json()["bundle"]["deadline_at"].startswith("2026-09-01T18:00")


def test_a_deadline_typed_into_the_request_is_ignored_when_an_assignment_is_named(app_client):
    """Свой срок в теле запроса не должен переигрывать срок потока.

    Иначе поле остаётся ровно тем, чем было: местом для опечатки, которая
    даёт необъяснимый штраф.
    """
    client = app_client(responses=[VERDICTS, VERDICTS], role="methodist")
    stream_id = _course_and_stream(client)
    assignment = _assignment(client, stream_id, deadline_at=DEADLINE)

    response = client.post(
        "/review",
        json={
            "link": LINK,
            "assignment_id": assignment["id"],
            "deadline_at": "2020-01-01T00:00:00+00:00",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["bundle"]["deadline_at"].startswith(
        "2026-09-01T18:00"
    ), "срок взят из формы, а не из задания"


def test_naming_both_an_assignment_and_a_rubric_is_refused(app_client):
    """Две рубрики в одном запросе — это работа, оценённая не по той."""
    client = app_client(role="methodist")
    stream_id = _course_and_stream(client)
    assignment = _assignment(client, stream_id)

    response = client.post(
        "/review",
        json={"link": LINK, "assignment_id": assignment["id"], "rubric_id": "go-task1"},
    )
    assert response.status_code == 422


def test_a_review_without_an_assignment_still_works(app_client):
    """Разбор по прямой ссылке на рубрику остаётся: он нужен, пока поток не заведён."""
    client = app_client(responses=[VERDICTS, VERDICTS], role="methodist")
    response = client.post("/review", json={"link": LINK, "rubric_id": "go-task1"})
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# целостность каталога
# --------------------------------------------------------------------------- #

def test_an_assignment_cannot_point_at_a_rubric_that_does_not_exist(app_client):
    client = app_client(role="methodist")
    stream_id = _course_and_stream(client)
    response = client.post(
        "/assignments", json={"stream_id": stream_id, "rubric_key": "нет-такой"}
    )
    assert response.status_code == 404


def test_one_rubric_is_handed_to_a_stream_only_once(app_client):
    client = app_client(role="methodist")
    stream_id = _course_and_stream(client)
    _assignment(client, stream_id)
    again = client.post("/assignments", json={"stream_id": stream_id, "rubric_key": "go-task1"})
    assert again.status_code == 409


def test_an_assignment_with_submissions_is_not_deleted(app_client):
    """Сдача ссылается на задание — удалив его, мы оставим её без объяснения срока."""
    client = app_client(responses=[VERDICTS, VERDICTS], role="methodist")
    stream_id = _course_and_stream(client)
    assignment = _assignment(client, stream_id, deadline_at=DEADLINE)
    client.post("/review", json={"link": LINK, "assignment_id": assignment["id"]})

    response = client.delete(f"/assignments/{assignment['id']}")
    assert response.status_code == 409


def test_the_deadline_can_be_cleared_but_not_by_passing_null(app_client):
    """`None` неотличим от «не передавали», поэтому дату снимают флагом."""
    client = app_client(role="methodist")
    stream_id = _course_and_stream(client)
    assignment = _assignment(client, stream_id, deadline_at=DEADLINE)

    untouched = client.patch(f"/assignments/{assignment['id']}", json={"title": "ДЗ 1"})
    assert untouched.json()["deadline_at"] is not None
    assert untouched.json()["title"] == "ДЗ 1"

    cleared = client.patch(f"/assignments/{assignment['id']}", json={"clear_deadline": True})
    assert cleared.json()["deadline_at"] is None


def test_only_students_are_enrolled(app_client):
    client = app_client(role="admin")
    stream_id = _course_and_stream(client)
    response = client.post(f"/streams/{stream_id}/students", json={"usernames": ["reviewer"]})
    assert response.status_code == 422

    ok = client.post(f"/streams/{stream_id}/students", json={"usernames": ["student"]})
    assert ok.json() == {"enrolled": 1, "already": 0}
    repeat = client.post(f"/streams/{stream_id}/students", json={"usernames": ["student"]})
    assert repeat.json() == {"enrolled": 0, "already": 1}


# --------------------------------------------------------------------------- #
# правка и удаление каталога
# --------------------------------------------------------------------------- #

def test_a_course_is_renamed_but_its_key_stays(app_client):
    """Ключ курса — то слово, которым его называют карточки ревьюеров."""
    client = app_client(role="admin")
    course = client.post("/courses", json={"key": "go", "title": "Go"}).json()
    renamed = client.patch(f"/courses/{course['id']}", json={"title": "Разработка на Go"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json() == {**course, "title": "Разработка на Go"}


def test_a_course_with_streams_is_not_deleted(app_client):
    client = app_client(role="admin")
    stream_id = _course_and_stream(client)
    course_id = client.get("/courses").json()[0]["id"]
    assert client.delete(f"/courses/{course_id}").status_code == 409

    assert client.delete(f"/streams/{stream_id}").status_code == 204
    assert client.delete(f"/courses/{course_id}").status_code == 204
    assert client.get("/courses").json() == []


def test_a_stream_with_assignments_or_students_is_not_deleted(app_client):
    client = app_client(role="admin")
    stream_id = _course_and_stream(client)
    _assignment(client, stream_id)
    assert client.delete(f"/streams/{stream_id}").status_code == 409

    assignment_id = client.get("/assignments").json()[0]["id"]
    assert client.delete(f"/assignments/{assignment_id}").status_code == 204
    client.post(f"/streams/{stream_id}/students", json={"usernames": ["student"]})
    assert client.delete(f"/streams/{stream_id}").status_code == 409

    assert client.delete(f"/streams/{stream_id}/students/student").status_code == 204
    assert client.delete(f"/streams/{stream_id}").status_code == 204


def test_a_stream_key_stays_unique_inside_its_course(app_client):
    client = app_client(role="admin")
    first = _course_and_stream(client)
    course_id = client.get("/courses").json()[0]["id"]
    client.post("/streams", json={"course_id": course_id, "key": "b", "title": "Весна"})

    clash = client.patch(f"/streams/{first}", json={"key": "b"})
    assert clash.status_code == 409

    renamed = client.patch(f"/streams/{first}", json={"key": "c", "title": "Осень 2027"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["key"] == "c"
    assert renamed.json()["title"] == "Осень 2027"


def test_the_roster_of_a_stream_is_readable_and_unenrolling_is_not_deleting(app_client):
    client = app_client(role="admin")
    stream_id = _course_and_stream(client)
    client.post(f"/streams/{stream_id}/students", json={"usernames": ["student"]})

    roster = client.get(f"/streams/{stream_id}/students").json()
    assert [row["username"] for row in roster] == ["student"]

    assert client.delete(f"/streams/{stream_id}/students/student").status_code == 204
    assert client.get(f"/streams/{stream_id}/students").json() == []
    # Аккаунт остался — отчисление снимает доступ к заданиям, а не удаляет человека.
    assert any(u["username"] == "student" for u in client.get("/users").json())


def test_unknown_course_stream_or_student_is_404(app_client):
    client = app_client(role="admin")
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.patch(f"/courses/{missing}", json={"title": "нет"}).status_code == 404
    assert client.delete(f"/courses/{missing}").status_code == 404
    assert client.patch(f"/streams/{missing}", json={"title": "нет"}).status_code == 404
    assert client.delete(f"/streams/{missing}").status_code == 404
    assert client.get(f"/streams/{missing}/students").status_code == 404

    stream_id = _course_and_stream(client)
    assert client.delete(f"/streams/{stream_id}/students/nobody").status_code == 404
    assert client.delete(f"/streams/{stream_id}/students/student").status_code == 404


def test_a_reviewer_cannot_delete_a_course_or_a_stream(app_client):
    admin = app_client(role="admin")
    stream_id = _course_and_stream(admin)
    course_id = admin.get("/courses").json()[0]["id"]

    reviewer = app_client(role="reviewer")
    assert reviewer.delete(f"/courses/{course_id}").status_code == 403
    assert reviewer.delete(f"/streams/{stream_id}").status_code == 403
    assert reviewer.patch(f"/streams/{stream_id}", json={"title": "чужое"}).status_code == 403
