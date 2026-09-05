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
