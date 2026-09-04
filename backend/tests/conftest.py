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

from avito_reviewer.config import AIConfig, IngestConfig  # noqa: E402

_SETTINGS = (AIConfig, IngestConfig)
_PREFIXES = ("AI_", "INGEST_")


@pytest.fixture(autouse=True)
def hermetic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрезать конфиги от `.env` и от переменных окружения разработчика."""
    for name in list(os.environ):
        if name.startswith(_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    for settings in _SETTINGS:
        monkeypatch.setitem(settings.model_config, "env_file", None)
