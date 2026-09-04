"""Загрузчик каталога для демо.

Скрипт, а не слой, но ломается он молча и ровно в тот момент, когда демо
показывают. Проверяется то, что демо обещает: роли расставлены, тела на месте,
история читается из git, а её отсутствие не считается ошибкой.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import local_bundle  # noqa: E402

from avito_reviewer.ai.content import build_texts  # noqa: E402
from avito_reviewer.ingest import ArtifactRole  # noqa: E402

MAIN = 'package main\n\nfunc main() {\n\tprintln("hi")\n}\n'


@pytest.fixture
def solution(tmp_path):
    (tmp_path / "cmd").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "vendor").mkdir()

    (tmp_path / "cmd" / "main.go").write_text(MAIN, encoding="utf-8")
    (tmp_path / "README.md").write_text("# сервис\n\nописание\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM golang:1.22\n", encoding="utf-8")
    (tmp_path / "go.sum").write_text("hash\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (tmp_path / "vendor" / "dep.go").write_text("package dep\n", encoding="utf-8")
    (tmp_path / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


def paths(bundle) -> set[str]:
    return {a.path for a in bundle.artifacts}


def test_solution_files_are_loaded_with_bodies(solution):
    bundle = local_bundle.load(solution)
    main = next(a for a in bundle.artifacts if a.path == "cmd/main.go")

    assert main.role is ArtifactRole.SOLUTION
    assert main.lang == "go"
    assert main.excerpt == MAIN
    assert main.line_count == 5


def test_tooling_is_marked_not_dropped(solution):
    """Оценивать его не надо, а видеть в сдаче — надо."""
    roles = {a.path: a.role for a in local_bundle.load(solution).artifacts}
    assert roles["Dockerfile"] is ArtifactRole.TOOLING
    assert roles[".github/workflows/ci.yml"] is ArtifactRole.TOOLING


def test_noise_and_binaries_never_get_read(solution):
    """mlruns на 314 файлов — это выхлоп инструмента, а не работа студента."""
    loaded = paths(local_bundle.load(solution))
    assert "vendor/dep.go" not in loaded
    assert "plot.png" not in loaded
    assert "go.sum" not in loaded


def test_the_repo_map_counts_what_the_artifacts_skip(solution):
    bundle = local_bundle.load(solution)
    assert "plot.png" in bundle.repo.files
    assert bundle.repo.total_files > len(bundle.artifacts)


def test_bundle_feeds_the_ai_layer_unchanged(solution):
    """Смысл загрузчика — в том, что дальше идёт обычный путь слоя."""
    import asyncio

    texts = asyncio.run(build_texts(local_bundle.load(solution)))
    assert {t.path for t in texts} >= {"cmd/main.go", "README.md"}
    assert all(not t.partial for t in texts)


def test_a_snapshot_without_git_has_no_history(solution):
    """Выгрузки организаторов приходят без .git — это не ошибка, это ограничение."""
    bundle = local_bundle.load(solution)
    assert bundle.revisions == []
    assert bundle.head_ref is None


def test_git_history_is_read_when_present(solution):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git недоступен")

    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(solution), *args], capture_output=True, check=True
    )
    run("init", "-q")
    run("config", "user.email", "d@e.f")
    run("config", "user.name", "dev")
    run("add", "-A")
    run("commit", "-qm", "init")

    bundle = local_bundle.load(solution)
    assert len(bundle.revisions) == 1
    assert bundle.revisions[0].summary == "init"
    assert bundle.revisions[0].added_lines > 0
    assert bundle.head_ref == bundle.revisions[0].id
