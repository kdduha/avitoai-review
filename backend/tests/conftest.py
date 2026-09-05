"""Общая настройка тестов.

Тесты не должны зависеть от того, что лежит в `.env` у разработчика: иначе
чужой ключ в рабочей копии меняет результат прогона, и «у меня всё зелёное»
перестаёт что-либо значить. Поэтому конфиги в тестах читаются только из
значений по умолчанию.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Фабрики моделей лежат рядом с тестами.
sys.path.insert(0, str(Path(__file__).parent))

from avito_reviewer.config import (  # noqa: E402
    AIConfig,
    AuthConfig,
    DatabaseConfig,
    IngestConfig,
    QueueConfig,
)

_SETTINGS = (AIConfig, IngestConfig, DatabaseConfig, AuthConfig, QueueConfig)
_PREFIXES = ("AI_", "INGEST_", "DB_", "AUTH_", "QUEUE_")


@pytest.fixture(autouse=True)
def hermetic_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Отрезать конфиги от `.env` и от переменных окружения разработчика.

    `DB_DSN` дополнительно указывает на файловый SQLite в `tmp_path`: прогон
    не должен требовать поднятого Postgres, а `:memory:` не годится — каждое
    новое соединение в пуле открыло бы отдельную пустую базу.
    """
    for name in list(os.environ):
        if name.startswith(_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    for settings in _SETTINGS:
        monkeypatch.setitem(settings.model_config, "env_file", None)
    monkeypatch.setenv("DB_DSN", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")


def login(client, role: str, *, password: str = "avito2026") -> str:
    """Bearer token for one of the four seeded accounts (username == role)."""
    response = client.post("/auth/login", json={"username": role, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def as_role(client, role: str) -> None:
    """Attach a seeded role's token to every subsequent request `client` makes."""
    client.headers["Authorization"] = f"Bearer {login(client, role)}"
