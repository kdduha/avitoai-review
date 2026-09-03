"""Минимальный загрузчик сдачи для демонстраций.

Нормализация — задача `reviewer-core`, и если он установлен, используется он.
Этот модуль существует только чтобы репозиторий можно было запустить, пока
ядро дорабатывается: он читает каталог, отбрасывает очевидный мусор и
собирает объекты нужной формы. Ни в какие сервисы он не входит.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {
    ".go", ".py", ".js", ".ts", ".java", ".rs", ".sql", ".sh",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".mod", ".example",
}
SKIP_DIRS = {".git", "mlruns", "__pycache__", "node_modules", "vendor", ".venv", "wandb"}
SKIP_NAMES = {"go.sum", "package-lock.json", "poetry.lock", ".ds_store"}


@dataclass
class Artifact:
    path: str
    text: str
    id: str
    language: str | None = None
    est_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    segments: list[Any] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.split("/")[-1]


@dataclass
class HistoryEvent:
    at: datetime
    added: int = 0
    removed: int = 0
    author_hash: str | None = None
    touched_paths: list[str] = field(default_factory=list)
    message: str | None = None


@dataclass
class Bundle:
    assignment_id: str
    files: list[Artifact] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)
    stage: str | None = None
    submitted_at: datetime | None = None
    deadline_at: datetime | None = None

    @property
    def solution_files(self) -> list[Artifact]:
        return self.files


def load(root: str | Path, assignment_id: str = "demo") -> Bundle:
    root = Path(root)
    bundle = Bundle(assignment_id=assignment_id)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in SKIP_DIRS for part in relative.parts):
            continue
        if path.name.lower() in SKIP_NAMES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name.lower() not in {
            "dockerfile", "makefile"
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        rel = relative.as_posix()
        bundle.files.append(
            Artifact(
                path=rel,
                text=text,
                id=hashlib.sha1(rel.encode()).hexdigest()[:12],
                language=path.suffix.lstrip(".") or None,
                est_tokens=int(len(text) / 3.3),
            )
        )

    bundle.history = read_git_log(root)
    return bundle


def read_git_log(repo: Path, limit: int = 300) -> list[HistoryEvent]:
    if not (repo / ".git").exists():
        return []
    try:
        raw = subprocess.run(
            ["git", "-C", str(repo), "log", "--pretty=format:%H\x1f%at\x1f%ae\x1f%s",
             "--numstat", f"-{limit}"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []

    events: list[HistoryEvent] = []
    current: HistoryEvent | None = None
    for line in raw.splitlines():
        if "\x1f" in line:
            if current:
                events.append(current)
            _, ts, email, message = line.split("\x1f", 3)
            current = HistoryEvent(
                at=datetime.fromtimestamp(int(ts), tz=timezone.utc),
                author_hash=hashlib.sha256(email.encode()).hexdigest()[:16],
                message=message,
            )
        elif line.strip() and current:
            parts = line.split("\t")
            if len(parts) == 3:
                added, removed, name = parts
                current.added += int(added) if added.isdigit() else 0
                current.removed += int(removed) if removed.isdigit() else 0
                current.touched_paths.append(name)
    if current:
        events.append(current)
    return list(reversed(events))
