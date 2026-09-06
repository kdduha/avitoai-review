"""Аутентификация и RBAC: три сеяных роли, JWT, лестница доступа.

Собственный `make_client` — не тот, что в `test_api.py`: тому не нужен ingest
или AIService для большинства сценариев здесь, только приложение и его база.
"""

from __future__ import annotations

import pytest
from conftest import as_role, login
from fastapi.testclient import TestClient

from avito_reviewer.app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# логин
# --------------------------------------------------------------------------- #

def test_seeded_accounts_exist_for_every_role(client):
    for role in ("student", "reviewer", "admin"):
        token = login(client, role)
        assert token


def test_wrong_password_is_401(client):
    response = client.post("/auth/login", json={"username": "reviewer", "password": "не тот"})
    assert response.status_code == 401


def test_unknown_username_is_401_not_500(client):
    response = client.post("/auth/login", json={"username": "нет такого", "password": "x"})
    assert response.status_code == 401


def test_demo_login_hands_out_a_reviewer_token_without_a_password(client):
    body = client.post("/auth/demo").json()
    assert body["role"] == "reviewer"

    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    assert client.get("/me").json()["username"] == "reviewer"


def test_demo_login_is_advertised_in_init(client):
    assert client.get("/init").json()["demo_login"] is True


def test_demo_login_switched_off_is_404_and_not_advertised(client):
    client.app.state.auth_config.demo_login = False
    assert client.post("/auth/demo").status_code == 404
    assert client.get("/init").json()["demo_login"] is False


def test_demo_login_without_the_seeded_reviewer_is_404_not_500(client):
    as_role(client, "admin")
    users = client.get("/users").json()
    reviewer = next(row for row in users if row["username"] == "reviewer")
    assert client.delete(f"/users/{reviewer['id']}").status_code == 204

    del client.headers["Authorization"]
    assert client.post("/auth/demo").status_code == 404


def test_me_reports_the_bearer_tokens_identity(client):
    as_role(client, "reviewer")
    body = client.get("/me").json()
    assert body["username"] == "reviewer"
    assert body["role"] == "reviewer"


# --------------------------------------------------------------------------- #
# RBAC — лестница доступа
# --------------------------------------------------------------------------- #

def test_no_token_is_401(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me/queue").status_code == 401


def test_garbage_token_is_401(client):
    client.headers["Authorization"] = "Bearer not-a-real-token"
    assert client.get("/me").status_code == 401


@pytest.mark.parametrize("role", ["student", "reviewer"])
def test_below_admin_cannot_reach_admin_routes(client, role):
    as_role(client, role)
    assert client.get("/cost").status_code == 403
    assert client.post("/rubrics", json={"rubric": {}, "confirmed_by": "x"}).status_code == 403


def test_student_cannot_reach_reviewer_routes(client):
    """`student` не имеет UI в MVP (§2 архитектуры) — и API тоже."""
    as_role(client, "student")
    assert client.get("/me/queue").status_code == 403
    assert client.get("/rubrics").status_code == 403


def test_reviewer_reaches_reviewer_routes_but_not_admin_ones(client):
    as_role(client, "reviewer")
    assert client.get("/me/queue").status_code == 200
    assert client.get("/rubrics").status_code == 200
    assert client.get("/cost").status_code == 403


def test_admin_reaches_everything_reviewer_does(client):
    as_role(client, "admin")
    assert client.get("/me/queue").status_code == 200
    assert client.get("/cost").status_code == 200


def test_the_reviewer_roster_becomes_accounts(client):
    """Каталог ревьюеров — данные; без аккаунтов их некуда приложить.

    Назначить на поток можно только строку `users`, поэтому десять настоящих
    карточек с навыками и ёмкостью оставались бы невидимыми, а в интерфейсе
    стояли бы два ревьюера с ёмкостью по умолчанию.
    """
    as_role(client, "admin")
    usernames = {u["username"] for u in client.get("/users").json()}

    assert "c-bahtin" in usernames, "карточка каталога завела аккаунт"
    assert {"student", "reviewer", "methodist", "admin"} <= usernames, "сеяные никуда не делись"

    roster = client.get("/users").json()
    card = next(u for u in roster if u["username"] == "c-bahtin")
    assert card["role"] == "reviewer"
    assert card["display_name"] == "Данил Бахтин", "имя берётся из карточки, а не из логина"


def test_seeding_the_roster_twice_adds_nothing(client):
    """Идемпотентно по логину: перезапуск не плодит и не переписывает."""
    import asyncio

    from avito_reviewer.app.auth import seed_roster_reviewers
    from avito_reviewer.config import AuthConfig

    as_role(client, "admin")
    before = len(client.get("/users").json())

    app = client.app

    async def again() -> int:
        async with app.state.sessionmaker() as session:
            return await seed_roster_reviewers(session, AuthConfig(), app.state.reviewers)

    assert asyncio.run(again()) == 0
    assert len(client.get("/users").json()) == before
