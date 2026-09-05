"""Тесты Format Gate — проверок, которые не стоят ни одного токена."""

from __future__ import annotations

from pathlib import Path

from factories import artifact, go_bundle, go_rubric, partial_artifact, texts_of

from avito_reviewer.ai import gate
from avito_reviewer.ai.gate import GateStatus
from avito_reviewer.ai.rubric import FormatCheck, Rubric, load_rubric

RUBRICS = Path(__file__).resolve().parents[1] / "rubrics"

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


def test_a_missing_blocking_string_is_reported_but_does_not_stop_the_review():
    """Непройденное дословное требование — повод рассказать, а не остановить.

    Раньше оно возвращало работу ревьюеру, не запуская модель: студент за одну
    недостающую строку в логе не получал ни слова о том, что сделано хорошо.
    """
    report = run_on(
        rubric_with(CONTAINS), artifact("cmd/main.go", text="package main\nfunc main() {}\n")
    )

    assert report.status is GateStatus.WARNING
    assert [o.label for o in report.failures] == ["Сообщение о завершении"]
    assert [o.level for o in report.failures] == ["blocking"], "важность проверки осталась"


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
    # Строка есть, но в markdown: проверка ищет только в коде, поэтому она не
    # засчитана — и это видно в статусе, а не в остановленном разборе.
    assert report.status is GateStatus.WARNING
    assert [o.label for o in report.failures] == ["Сообщение о завершении"]


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
# история ревизий
# --------------------------------------------------------------------------- #

HISTORY = {
    "check": "revision_history_visible",
    "level": "blocking",
    "params": {"label": "Видна история изменений"},
}


def test_git_history_answers_a_check_written_for_google_docs():
    """Требование про историю изменений написано под Docs, но git на него отвечает."""
    report = run_on(rubric_with(HISTORY))

    assert report.status is GateStatus.PASSED
    assert report.outcomes[0].passed is True
    assert "коммитов: 2" in report.outcomes[0].detail


def test_history_that_never_arrived_is_not_a_missing_history():
    """Pull request без коммитов не бывает: пустота здесь — молчание источника."""
    bundle = go_bundle(revisions=[])
    report = gate.run(bundle, texts_of(bundle), rubric_with(HISTORY))
    outcome = report.outcomes[0]

    assert outcome.inconclusive is True
    assert outcome.passed is False
    assert report.status is GateStatus.WARNING


def test_the_shipped_sysdesign_rubric_answers_history_and_still_defers_the_font():
    """На настоящей рубрике каталога: историю закрыли, шрифт остался за git-каналом."""
    rubric = load_rubric(RUBRICS / "sysdesign-lab1.json")
    bundle = go_bundle()
    outcomes = {o.check: o for o in gate.run(bundle, texts_of(bundle), rubric).outcomes}

    assert outcomes["revision_history_visible"].passed is True
    assert outcomes["revision_history_visible"].inconclusive is False
    assert outcomes["font"].inconclusive is True


# --------------------------------------------------------------------------- #
# отчёт
# --------------------------------------------------------------------------- #

def test_unknown_check_does_not_break_the_run():
    """Рубрику пишет методист, и она обгонит код: незнакомая проверка не роняет прогон.

    Но и не пропадает — иначе «гейт пройден» скажет о том, чего не смотрели.
    """
    report = run_on(rubric_with({"check": "font_size", "level": "blocking", "params": {}}))

    assert [o.check for o in report.outcomes] == ["font_size"]
    assert report.outcomes[0].inconclusive is True
    assert report.status is GateStatus.WARNING


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


def test_unimplemented_check_goes_to_the_reviewer_instead_of_vanishing():
    """Часть требований условия исполняется только другим каналом сдачи.

    Шрифт и число страниц живут в Google Docs, а не в git. Молча пропустить
    такую проверку значит выдать «гейт пройден» за работу, которую никто не
    проверял, — а если она блокирующая, то и пропустить её мимо ревьюера.
    """
    rubric = rubric_with(
        {"check": "font", "level": "blocking",
         "params": {"family": "Arial", "size_pt": 11, "label": "Шрифт Arial 11"}}
    )
    report = run_on(rubric)
    outcome = report.outcomes[0]

    assert outcome.inconclusive is True
    assert outcome.passed is False
    # Непроверенное — не то же самое, что проваленное, и оба не останавливают.
    assert report.status is GateStatus.WARNING
    assert outcome in report.unresolved
