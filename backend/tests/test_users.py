"""Управление аккаунтами: единственный способ завести второго ревьюера для
теста, не трогая базу руками."""

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


def test_reviewer_cannot_manage_users(client):
    as_role(client, "reviewer")
    assert client.get("/users").status_code == 403
    assert client.post(
        "/users", json={"username": "x", "password": "xxxx", "role": "reviewer"}
    ).status_code == 403


def test_admin_creates_lists_and_logs_into_a_new_reviewer(client):
    as_role(client, "admin")
    created = client.post(
        "/users",
        json={"username": "reviewer-2", "password": "s3cret!", "role": "reviewer", "display_name": "Второй ревьюер"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["username"] == "reviewer-2"

    listed = client.get("/users").json()
    assert any(u["username"] == "reviewer-2" for u in listed)

    token = login(client, "reviewer-2", password="s3cret!")
    assert token


def test_creating_a_duplicate_username_is_409(client):
    as_role(client, "admin")
    body = {"username": "reviewer-dup", "password": "s3cret!", "role": "reviewer"}
    assert client.post("/users", json=body).status_code == 201
    assert client.post("/users", json=body).status_code == 409


def test_patch_changes_role_and_password(client):
    as_role(client, "admin")
    user_id = client.post(
        "/users", json={"username": "promote-me", "password": "old-pass", "role": "reviewer"}
    ).json()["id"]

    updated = client.patch(f"/users/{user_id}", json={"role": "admin", "password": "new-pass"})
    assert updated.status_code == 200
    assert updated.json()["role"] == "admin"

    assert login(client, "promote-me", password="new-pass")
    with pytest.raises(AssertionError):
        login(client, "promote-me", password="old-pass")


def test_delete_removes_the_account(client):
    as_role(client, "admin")
    user_id = client.post(
        "/users", json={"username": "throwaway", "password": "xxxxxxxx", "role": "reviewer"}
    ).json()["id"]

    assert client.delete(f"/users/{user_id}").status_code == 204
    assert client.get(f"/users/{user_id}").status_code == 404


def test_get_and_delete_unknown_user_is_404(client):
    as_role(client, "admin")
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/users/{fake_id}").status_code == 404
    assert client.delete(f"/users/{fake_id}").status_code == 404


def test_cannot_delete_the_last_admin(client):
    """Seeding only fills an *empty* table (`app/auth.py`) — losing the last
    admin this way is a permanent lockout, not something a restart undoes."""
    as_role(client, "admin")
    admin_id = next(u["id"] for u in client.get("/users").json() if u["username"] == "admin")

    assert client.delete(f"/users/{admin_id}").status_code == 409
    assert client.get(f"/users/{admin_id}").status_code == 200


def test_cannot_demote_the_last_admin(client):
    as_role(client, "admin")
    admin_id = next(u["id"] for u in client.get("/users").json() if u["username"] == "admin")

    assert client.patch(f"/users/{admin_id}", json={"role": "reviewer"}).status_code == 409
    assert client.get(f"/users/{admin_id}").json()["role"] == "admin"


def test_second_admin_can_be_deleted_and_demoted(client):
    """The guard is about the *last* admin, not admins in general."""
    as_role(client, "admin")
    second_id = client.post(
        "/users", json={"username": "admin-2", "password": "s3cret!!", "role": "admin"}
    ).json()["id"]

    assert client.patch(f"/users/{second_id}", json={"role": "reviewer"}).status_code == 200

    third_id = client.post(
        "/users", json={"username": "admin-3", "password": "s3cret!!", "role": "admin"}
    ).json()["id"]
    assert client.delete(f"/users/{third_id}").status_code == 204
