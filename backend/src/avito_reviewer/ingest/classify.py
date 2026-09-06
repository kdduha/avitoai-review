"""Что в сдаче — работа студента, а что выхлоп инструмента.

В «хорошем решении» курса LLM лежит `mlruns/` на 314 файлов трекинга MLflow —
след запуска, а не работа. Туда же `go.sum`, `__pycache__`, локфайлы. Класс
артефакта решает, куда он попадёт:

- `solution` — в ревью и в детектор;
- `evidence` — графики и скриншоты: учитываются по факту наличия;
- `tooling` — `Dockerfile`, CI, миграции, сгенерированные `*.pb.go`. **Из
  детектора исключается тоже**: сгенерированный код ничего не говорит о
  самостоятельности студента, а детектор без этого ловит сам себя;
- `noise` — никуда.

Правило жило в трёх местах сразу и в каждом по-своему: денилист в конфиге
ingest, список шаблонов в судье детектора, своя разметка в демо-скрипте. Боевой
провайдер `tooling` не ставил вовсе, и служебный код уходил в детектор как
работа студента.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import ArtifactRole

NOISE_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "vendor", "__pycache__",
    "mlruns", "wandb", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    "dist", "build", "target", ".next", "coverage", "htmlcov",
})
NOISE_NAMES = frozenset({
    "go.sum", "package-lock.json", "poetry.lock", "yarn.lock", "pnpm-lock.yaml",
    "uv.lock", "cargo.lock", "composer.lock", ".ds_store", "thumbs.db",
})
NOISE_SUFFIXES = (".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe", ".zip", ".tar", ".gz")

TOOLING_DIRS = frozenset({".github", ".gitlab", "ci", "deploy", "migrations", "migration", "alembic"})
TOOLING_NAMES = frozenset({
    "dockerfile", "makefile", "docker-compose.yml", "docker-compose.yaml",
    ".gitignore", ".dockerignore", ".editorconfig", ".env.example",
    "go.mod", "requirements.txt", "poetry.toml", "setup.cfg", "setup.py",
})
TOOLING_PATTERNS = (
    re.compile(r"\.pb\.go$"),
    re.compile(r"_pb2(_grpc)?\.py$"),
    re.compile(r"\.generated\.[a-z]+$"),
    re.compile(r"(^|/)\.github/"),
)

EVIDENCE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp")
"""Графики и скриншоты. Роль у них не `noise` намеренно: работа, к которой
приложен график, отличается от работы без него, и ревьюер должен это видеть —
даже когда прочесть картинку нечем."""


def classify(path: str) -> ArtifactRole:
    """Класс артефакта по его пути. Ни одного обращения к содержимому."""
    relative = PurePosixPath(path)
    name = relative.name.lower()
    parents = {part.lower() for part in relative.parts[:-1]}

    if parents & NOISE_DIRS or name in NOISE_NAMES or name.endswith(NOISE_SUFFIXES):
        return ArtifactRole.NOISE
    if name.endswith(EVIDENCE_SUFFIXES):
        return ArtifactRole.EVIDENCE
    if (
        name in TOOLING_NAMES
        or parents & TOOLING_DIRS
        or any(pattern.search(path) for pattern in TOOLING_PATTERNS)
    ):
        return ArtifactRole.TOOLING
    return ArtifactRole.SOLUTION
