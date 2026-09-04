"""Тесты Format Gate — проверок, которые не стоят ни одного токена."""

from __future__ import annotations

from factories import artifact, go_bundle, go_rubric, partial_artifact, texts_of

from avito_reviewer.ai import gate
from avito_reviewer.ai.gate import GateStatus
from avito_reviewer.ai.rubric import FormatCheck, Rubric

GO_MAIN_MIN = 'package main\n\nfunc main() {\n\tlog.Println("Shutting down service-courier")\n}\n'


def rubric_with(*checks: dict) -> Rubric:
    return go_rubric(format_gate=[FormatCheck(**check) for check in checks])


def run_on(rubric: Rubric, *artifacts) -> gate.GateReport:
    kwargs = {"repo": None}
    if artifacts:
        kwargs["artifacts"] = list(artifacts)
    bundle = go_bundle(**kwargs)
    return gate.run(bundle, texts_of(bundle), rubric)


# --------------------------------------------------------------------------- #
# присутствие строки в коде
# --------------------------------------------------------------------------- #

CONTAINS = {
    "check": "code_contains",
    "level": "blocking",
    "params": {
        "pattern": "Shutting down service-courier",
        "label": "Сообщение о завершении",
        "expected": "строка «Shutting down service-courier»",
        "in": [".go"],
    },
}


def test_present_string_passes_and_points_at_the_line():
    """Факт должен быть кликабельным: ревьюер идёт в строку, а не ищет глазами."""
    report = run_on(rubric_with(CONTAINS), artifact("cmd/main.go", text=GO_MAIN_MIN))

    assert report.status is GateStatus.PASSED
    assert report.outcomes[0].locations == ["cmd/main.go:4"]


def test_missing_blocking_string_blocks_the_submission():
    report = run_on(
        rubric_with(CONTAINS), artifact("cmd/main.go", text="package main\nfunc main() {}\n")
    )

    assert report.status is GateStatus.BLOCKED
    assert report.blocked is True
    assert [o.label for o in report.failures] == ["Сообщение о завершении"]


def test_absence_in_a_fragment_never_blocks():
    """Мы смотрели не весь файл — «этого нет» здесь недоказуемо."""
    report = run_on(rubric_with(CONTAINS), partial_artifact("cmd/main.go"))

    assert report.status is GateStatus.WARNING
    assert report.failures == []
    assert [o.label for o in report.unresolved] == ["Сообщение о завершении"]
    assert "фрагмент" in report.unresolved[0].detail


def test_only_listed_suffixes_are_searched():
    report = run_on(
        rubric_with(CONTAINS),
        artifact("README.md", text="Пишем Shutting down service-courier\n", lang="markdown"),
    )
    assert report.status is GateStatus.BLOCKED


# --------------------------------------------------------------------------- #
# пути
# --------------------------------------------------------------------------- #

def test_directory_requirement_is_satisfied_by_any_file_under_it():
    rubric = rubric_with(
        {"check": "required_paths", "level": "warning", "params": {"paths": ["cmd/", "internal/"]}}
    )
    report = run_on(
        rubric,
        artifact("cmd/main.go", text="package main\n"),
        artifact("internal/handler/ping.go", text="package handler\n"),
    )
    assert report.status is GateStatus.PASSED


def test_missing_directory_is_a_warning_not_a_block():
    rubric = rubric_with(
        {"check": "required_paths", "level": "warning", "params": {"paths": ["internal/"]}}
    )
    report = run_on(rubric, artifact("cmd/main.go", text="package main\n"))

    assert report.status is GateStatus.WARNING
    assert "internal/" in report.outcomes[0].detail


def test_required_paths_see_the_whole_repository_not_just_the_diff():
    """Каталог мог появиться в прошлой сдаче — требование к репозиторию, не к диффу."""
    rubric = rubric_with(
        {"check": "required_paths", "level": "warning", "params": {"paths": ["internal/"]}}
    )
    bundle = go_bundle(artifacts=[artifact("cmd/main.go", text="package main\n")])
    assert bundle.repo is not None
    bundle.repo.files = ["cmd/main.go", "internal/store/pg.go"]

    assert gate.run(bundle, texts_of(bundle), rubric).status is GateStatus.PASSED


def test_committed_secret_file_is_caught():
    rubric = rubric_with(
        {
            "check": "forbidden_paths",
            "level": "warning",
            "params": {"paths": [".env"], "label": "Реальный .env не закоммичен"},
        }
    )
    report = run_on(rubric, artifact(".env", text="TOKEN=secret\n", lang=None))

    assert report.status is GateStatus.WARNING
    assert report.outcomes[0].passed is False


# --------------------------------------------------------------------------- #
# отчёт
# --------------------------------------------------------------------------- #

def test_unknown_check_is_skipped_not_fatal():
    """Рубрику пишет методист, и она обгонит код: незнакомая проверка не должна ронять прогон."""
    report = run_on(rubric_with({"check": "font_size", "level": "blocking", "params": {}}))

    assert report.outcomes == []
    assert report.status is GateStatus.PASSED


def test_info_level_never_raises_the_status():
    rubric = rubric_with(
        {"check": "token_budget", "level": "info", "params": {"max_tokens": 1}}
    )
    report = run_on(rubric, artifact("cmd/main.go", text=GO_MAIN_MIN))

    assert report.outcomes[0].passed is False
    assert report.status is GateStatus.PASSED


def test_facts_carry_the_verdict_and_the_place():
    report = run_on(rubric_with(CONTAINS), artifact("cmd/main.go", text=GO_MAIN_MIN))
    assert report.facts == ["✓ Сообщение о завершении: найдено: строка «Shutting down service-courier» (cmd/main.go:4)"]


def test_empty_gate_is_a_pass():
    assert run_on(go_rubric()).status is GateStatus.PASSED
