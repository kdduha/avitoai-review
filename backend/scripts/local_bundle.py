"""Каталог с решением → `SubmissionBundle`.

Нужен ровно для одного: прогнать демо на реальных работах из
`homework_examples`, где нет ни PR, ни токена. Собирается тот же объект, что
отдал бы провайдер, — демо идёт по настоящему пути слоя, а не по параллельному.

Провайдером это намеренно не оформлено: `SubmissionProvider` — контракт для
источников сдач, а каталог на диске источником сдач не является. Заглушек под
нереализованные источники в коде не держим.

Честная оговорка: у снимка каталога нет ни PR, ни base..head. `source` и
`origin_url` здесь — заполнители, а весь файл считается добавленным этой
сдачей, потому что сравнивать не с чем.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from avito_reviewer.ingest import (
    Artifact,
    ArtifactRole,
    ChangeStatus,
    LineRange,
    RepoContext,
    Revision,
    StudentRef,
    SubmissionBundle,
    SubmissionSource,
)

TEXT_SUFFIXES = frozenset({
    ".go", ".py", ".js", ".ts", ".tsx", ".java", ".rs", ".sql", ".sh", ".md", ".txt",
    ".yaml", ".yml", ".toml", ".json", ".mod", ".cfg", ".ini", ".env", ".example",
})
NAMED_FILES = frozenset({"dockerfile", "makefile"})

SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "vendor", "__pycache__", "mlruns",
    "wandb", ".idea", ".vscode", "dist", "build",
})
NOISE_NAMES = frozenset({"go.sum", "package-lock.json", "poetry.lock", "yarn.lock", ".ds_store"})
TOOLING_NAMES = frozenset({"dockerfile", "makefile", "docker-compose.yml", "docker-compose.yaml"})
TOOLING_DIRS = frozenset({".github", "ci", "deploy", "migrations"})

LANGS = {
    ".go": "go", ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".java": "java", ".rs": "rust", ".sql": "sql",
    ".sh": "shell", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".json": "json", ".mod": "go",
}

MAX_FILES = 200


def _role(relative: PurePosixPath) -> ArtifactRole:
    name = relative.name.lower()
    if name in NOISE_NAMES:
        return ArtifactRole.NOISE
    if name in TOOLING_NAMES or set(relative.parts[:-1]) & TOOLING_DIRS:
        return ArtifactRole.TOOLING
    return ArtifactRole.SOLUTION


def _added_diff(text: str) -> str:
    lines = text.splitlines()
    return f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)


def _artifact(path: Path, relative: PurePosixPath, text: str) -> Artifact:
    lines = text.splitlines()
    return Artifact(
        path=str(relative),
        status=ChangeStatus.ADDED,
        role=_role(relative),
        lang=LANGS.get(path.suffix.lower()) or (relative.name.lower() if relative.name.lower() in NAMED_FILES else None),
        size_bytes=len(text.encode()),
        line_count=len(lines),
        changed_ranges=[LineRange(start=1, end=len(lines))] if lines else [],
        diff=_added_diff(text) if lines else None,
        excerpt=text,
        content_ref=None,
    )


def _readable(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name.lower() in NAMED_FILES


def read_revisions(root: Path, limit: int = 300) -> list[Revision]:
    """История из git, если каталог — репозиторий. Выгрузки-снимки её не имеют."""
    if not (root / ".git").exists():
        return []
    try:
        raw = subprocess.run(
            ["git", "-C", str(root), "log", "--pretty=format:%H\x1f%at\x1f%ae\x1f%s",
             "--numstat", f"-{limit}"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []

    revisions: list[Revision] = []
    current: Revision | None = None
    for line in raw.splitlines():
        if "\x1f" in line:
            if current:
                revisions.append(current)
            sha, timestamp, _email, subject = line.split("\x1f", 3)
            current = Revision(
                id=sha,
                authored_at=datetime.fromtimestamp(int(timestamp), tz=UTC),
                author_hash="local-author",
                summary=subject,
            )
        elif line.strip() and current:
            parts = line.split("\t")
            if len(parts) == 3:
                added, removed, _name = parts
                current.added_lines += int(added) if added.isdigit() else 0
                current.removed_lines += int(removed) if removed.isdigit() else 0
    if current:
        revisions.append(current)
    return list(reversed(revisions))


def load(root: str | Path, *, submitted_at: datetime | None = None,
         deadline_at: datetime | None = None) -> SubmissionBundle:
    root = Path(root)
    artifacts: list[Artifact] = []
    every_path: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if set(relative.parts) & SKIP_DIRS:
            continue
        every_path.append(str(relative))
        if not _readable(path) or len(artifacts) >= MAX_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        artifacts.append(_artifact(path, relative, text))

    revisions = read_revisions(root)
    submitted = submitted_at or (revisions[-1].authored_at if revisions else datetime.now(tz=UTC))

    return SubmissionBundle(
        source=SubmissionSource.GITHUB_PR,
        origin_url=root.resolve().as_uri(),
        retrieved_at=datetime.now(tz=UTC),
        student_ref=StudentRef(internal_id="local-demo"),
        submitted_at=submitted,
        deadline_at=deadline_at,
        base_ref=None,
        head_ref=revisions[-1].id if revisions else None,
        artifacts=artifacts,
        revisions=revisions,
        repo=RepoContext(
            root=root.name,
            total_files=len(every_path),
            files=sorted(every_path)[:500],
            truncated=len(every_path) > 500,
        ),
    )
