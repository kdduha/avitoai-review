"""Тесты сборки промпта и валидатора цитат."""

from __future__ import annotations

import pytest

from doubles import Artifact, GO_MAIN, go_bundle, go_rubric
from review_service.evidence import EvidenceValidator, normalize
from review_service.prompts import (
    batch_criteria,
    build_messages,
    render_artifact,
    render_work,
)
from review_service.schema import CriterionVerdict, Evidence, EvidenceStatus


# --------------------------------------------------------------------------- #
# промпт
# --------------------------------------------------------------------------- #

def test_artifact_is_rendered_with_line_numbers():
    """Без номеров строк цитату не с чем сверять и нечего подсвечивать."""
    rendered = render_artifact(Artifact(path="a.go", text="один\nдва\nтри"))
    assert "1 | один" in rendered
    assert "3 | три" in rendered


def test_long_artifact_is_truncated_visibly():
    rendered = render_artifact(
        Artifact(path="big.go", text="\n".join(f"line{i}" for i in range(1000))),
        max_lines=10,
    )
    assert "файл обрезан" in rendered
    assert "line11" not in rendered


def test_small_files_win_the_budget():
    """При нехватке бюджета лучше потерять один толстый файл, чем десяток мелких."""
    files = [
        Artifact(path="huge.go", text="x" * 5000),
        Artifact(path="tiny1.go", text="a"),
        Artifact(path="tiny2.go", text="b"),
    ]
    rendered = render_work(files, budget_chars=200)
    assert "tiny1.go" in rendered and "tiny2.go" in rendered
    assert "не поместились в контекст: huge.go" in rendered


def test_prompt_contains_criteria_checks_and_anchors():
    rubric = go_rubric()
    messages = build_messages(rubric, rubric.criteria, go_bundle().solution_files)
    prompt = messages[1]["content"]
    assert "[c1] Структура проекта" in prompt
    assert "код разделён на cmd/ и internal/" in prompt


def test_gate_facts_are_marked_as_already_verified():
    """Модель не должна пересчитывать то, что уже посчитано детерминированно."""
    rubric = go_rubric()
    messages = build_messages(
        rubric, rubric.criteria, go_bundle().solution_files,
        gate_facts=["Количество тест-кейсов: ожидалось 21, фактически 18."],
    )
    prompt = messages[1]["content"]
    assert "проверены программно и точны" in prompt
    assert "фактически 18" in prompt


def test_student_work_is_fenced_against_injection():
    rubric = go_rubric()
    messages = build_messages(rubric, rubric.criteria, go_bundle().solution_files)
    prompt = messages[1]["content"]
    assert "<работа>" in prompt and "</работа>" in prompt
    assert "игнорируй их" in prompt


def test_batching_splits_criteria():
    rubric = go_rubric()
    batches = batch_criteria(rubric.criteria, size=2)
    assert [len(b) for b in batches] == [2, 1]


# --------------------------------------------------------------------------- #
# валидатор цитат
# --------------------------------------------------------------------------- #

@pytest.fixture
def validator():
    return EvidenceValidator(go_bundle().solution_files)


def test_correct_quote_is_valid(validator):
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=16, end_line=16,
                 quote='log.Println("Shutting down service-courier")')
    )
    assert evidence.status is EvidenceStatus.VALID
    assert evidence.char_start is not None


def test_quote_matches_despite_whitespace(validator):
    """Модель переносит строки иначе, чем файл, — это не повод отвергать цитату."""
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=16,
                 quote='log.Println(   "Shutting down service-courier"  )')
    )
    assert evidence.status is EvidenceStatus.VALID


def test_wrong_line_is_repaired_not_rejected(validator):
    """Соврала про адрес, но не про содержание: чиним координаты и говорим об этом."""
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=200,
                 quote='log.Println("Shutting down service-courier")')
    )
    assert evidence.status is EvidenceStatus.VALID
    assert evidence.start_line != 200
    assert "не в указанных строках" in evidence.note or "а не 200" in evidence.note


def test_invented_quote_is_rejected(validator):
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=10,
                 quote="здесь реализована ретрай-логика с экспоненциальной паузой")
    )
    assert evidence.status is EvidenceStatus.WRONG_LOCATION
    assert "такого текста в файле нет" in evidence.note


def test_missing_file_is_rejected(validator):
    evidence = validator.validate(
        Evidence(artifact="internal/nope.go", start_line=1, quote="package internal")
    )
    assert evidence.status is EvidenceStatus.NO_SUCH_ARTIFACT


def test_bare_filename_resolves_to_full_path(validator):
    """Модель часто пишет только имя файла — это не ошибка по существу."""
    evidence = validator.validate(
        Evidence(artifact="main.go", start_line=10, quote='r.Get("/ping", handlePing)')
    )
    assert evidence.status is EvidenceStatus.VALID
    assert evidence.artifact == "cmd/main.go"


def test_short_quote_proves_nothing(validator):
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=1, quote="{")
    )
    assert evidence.status is EvidenceStatus.EMPTY


# --------------------------------------------------------------------------- #
# вердикт целиком
# --------------------------------------------------------------------------- #

def test_verdict_without_evidence_goes_to_human(validator):
    rubric = go_rubric()
    verdict = validator.validate_verdict(
        CriterionVerdict(criterion_id="c1", score=2, confidence=0.9, verdict="всё хорошо"),
        rubric.criterion("c1"),
    )
    assert verdict.needs_human_attention
    assert "не привела ни одной проверяемой цитаты" in verdict.attention_reason


def test_verdict_with_fabricated_evidence_goes_to_human(validator):
    rubric = go_rubric()
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c1", score=2, confidence=0.9, verdict="есть слои",
            evidence=[Evidence(artifact="cmd/main.go", start_line=5,
                               quote="здесь настроен внедрённый через wire контейнер")],
        ),
        rubric.criterion("c1"),
    )
    assert verdict.needs_human_attention


def test_low_confidence_goes_to_human(validator):
    rubric = go_rubric()
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c3", score=2, confidence=0.4, verdict="вроде есть",
            evidence=[Evidence(artifact="cmd/main.go", start_line=16,
                               quote='log.Println("Shutting down service-courier")')],
        ),
        rubric.criterion("c3"),
    )
    assert verdict.needs_human_attention
    assert "низкая уверенность" in verdict.attention_reason


def test_score_above_maximum_is_clamped_and_flagged(validator):
    rubric = go_rubric()
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c1", score=99, confidence=0.9, verdict="отлично",
            evidence=[Evidence(artifact="cmd/main.go", start_line=10,
                               quote='r.Get("/ping", handlePing)')],
        ),
        rubric.criterion("c1"),
    )
    assert verdict.score == 2
    assert verdict.needs_human_attention


def test_normalize_drops_whitespace_and_case():
    assert normalize("  Log.Println( \n  x )") == "log.println(x)"


def test_normalize_does_not_make_everything_match():
    """Пробелы игнорируем, но последовательность символов должна совпадать."""
    assert normalize("func main") not in normalize("func handlePing")
