"""Сборка промпта и валидатор цитат.

Валидатор — главный анти-галлюцинационный механизм системы, поэтому тестов на
него больше, чем на что-либо ещё, и половина из них про то, как он ошибается.
"""

from __future__ import annotations

import pytest
from factories import GO_MAIN, artifact, go_rubric, partial_artifact

from avito_reviewer.ai.content import from_artifact
from avito_reviewer.ai.review.evidence import EvidenceValidator, normalize
from avito_reviewer.ai.review.prompts import (
    batch_criteria,
    build_messages,
    render_artifact,
    render_work,
)
from avito_reviewer.ai.review.schema import CriterionVerdict, Evidence, EvidenceStatus


def text_of(*args, **kwargs):
    result = from_artifact(artifact(*args, **kwargs))
    assert result is not None
    return result


MAIN = lambda: text_of("cmd/main.go", text=GO_MAIN, changed=[(1, 24)])  # noqa: E731
PARTIAL = lambda: from_artifact(partial_artifact("internal/store/pg.go"))  # noqa: E731


# --------------------------------------------------------------------------- #
# промпт
# --------------------------------------------------------------------------- #

def test_artifact_is_rendered_with_line_numbers():
    """Без номеров строк цитату не с чем сверять и нечего подсвечивать."""
    rendered = render_artifact(text_of("a.go", text="один\nдва\nтри"))
    assert "1 | один" in rendered
    assert "3 | три" in rendered


def test_partial_artifact_carries_head_numbers_and_a_warning():
    """Номера — из файла, а не из нашего куска, иначе подсветка врёт."""
    rendered = render_artifact(PARTIAL())
    assert "ФРАГМЕНТ" in rendered
    assert "40 | " in rendered and "41 | " in rendered
    assert "Не делай по этому файлу выводов об отсутствии" in rendered


def test_gap_between_hunks_is_visible():
    """Иначе модель примет соседние строки за соседние в файле."""
    rendered = render_artifact(
        text_of(
            "a.go",
            diff=(
                "@@ -1,2 +1,2 @@\n one\n two\n"
                "@@ -50,2 +50,2 @@\n fifty\n fiftyone\n"
            ),
            size_bytes=9000,
        )
    )
    assert "⋯ пропущено" in rendered


def test_hunk_markers_never_reach_the_prompt():
    """Модель начинает цитировать `+` вместе с кодом, и цитата перестаёт совпадать."""
    rendered = render_artifact(PARTIAL())

    assert "@@" not in rendered
    assert "+\trows" not in rendered
    assert "rows, err := s.db.Query(ctx, q)" in rendered


def test_changed_lines_are_named():
    assert "Изменено в этой сдаче: строки 1–24" in render_artifact(MAIN())


def test_long_artifact_is_truncated_visibly():
    rendered = render_artifact(
        text_of("big.go", text="\n".join(f"line{i}" for i in range(1000))), max_lines=10
    )
    assert "показано 10 строк из 1000" in rendered
    assert "line11" not in rendered


def test_small_files_win_the_budget():
    """При нехватке бюджета лучше потерять один толстый файл, чем десяток мелких."""
    rendered = render_work(
        [
            text_of("huge.go", text="x" * 5000),
            text_of("tiny1.go", text="a"),
            text_of("tiny2.go", text="b"),
        ],
        budget_chars=200,
    )
    assert "tiny1.go" in rendered and "tiny2.go" in rendered
    assert "не поместились в контекст: huge.go" in rendered


def test_prompt_contains_criteria_checks_and_anchors():
    rubric = go_rubric()
    prompt = build_messages(rubric, rubric.criteria, [MAIN()])[1]["content"]
    assert "[c1] Структура проекта" in prompt
    assert "код разделён на cmd/ и internal/" in prompt


def test_prompt_forbids_absence_claims_about_fragments():
    """Вердикт «в работе нет обработки ошибок» по одному диффу — некорректный вердикт."""
    rubric = go_rubric()
    messages = build_messages(rubric, rubric.criteria, [MAIN(), PARTIAL()])
    assert "нельзя утверждать, что чего-то нет" in messages[0]["content"]
    assert "Показаны не целиком (ФРАГМЕНТ): internal/store/pg.go" in messages[1]["content"]


def test_prompt_says_nothing_about_fragments_when_there_are_none():
    rubric = go_rubric()
    prompt = build_messages(rubric, rubric.criteria, [MAIN()])[1]["content"]
    assert "Показаны не целиком" not in prompt


def test_gate_facts_are_marked_as_already_verified():
    """Модель не должна пересчитывать то, что уже посчитано детерминированно."""
    rubric = go_rubric()
    prompt = build_messages(
        rubric,
        rubric.criteria,
        [MAIN()],
        gate_facts=["Количество тест-кейсов: ожидалось 21, фактически 18."],
    )[1]["content"]
    assert "проверены программно и точны" in prompt
    assert "фактически 18" in prompt


def test_student_work_is_fenced_against_injection():
    rubric = go_rubric()
    prompt = build_messages(rubric, rubric.criteria, [MAIN()])[1]["content"]
    assert "<работа>" in prompt and "</работа>" in prompt
    assert "игнорируй их" in prompt


def test_batching_splits_criteria():
    assert [len(b) for b in batch_criteria(go_rubric().criteria, size=2)] == [2, 1]


# --------------------------------------------------------------------------- #
# валидатор цитат
# --------------------------------------------------------------------------- #

@pytest.fixture
def validator():
    return EvidenceValidator([MAIN()])


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
    assert evidence.start_line == 16
    assert "а не 200" in evidence.note


def test_invented_quote_is_rejected(validator):
    evidence = validator.validate(
        Evidence(artifact="cmd/main.go", start_line=10,
                 quote="здесь реализована ретрай-логика с экспоненциальной паузой")
    )
    assert evidence.status is EvidenceStatus.WRONG_LOCATION
    assert "такого текста в файле нет" in evidence.note


def test_missing_quote_in_a_fragment_is_not_called_a_lie():
    """Мы не видели файла целиком — обвинять модель в выдумке не на чем."""
    validator = EvidenceValidator([PARTIAL()])
    evidence = validator.validate(
        Evidence(artifact="internal/store/pg.go", start_line=300,
                 quote="func (s *Store) Close() error { return s.db.Close() }")
    )
    assert evidence.status is EvidenceStatus.NOT_IN_AVAILABLE_PART
    assert "показан фрагментом" in evidence.note


def test_quote_found_inside_a_fragment_is_valid_without_char_offsets():
    """Строки у фрагмента настоящие, а смещения в символах указывали бы в наш кусок."""
    validator = EvidenceValidator([PARTIAL()])
    evidence = validator.validate(
        Evidence(artifact="internal/store/pg.go", start_line=41,
                 quote="rows, err := s.db.Query(ctx, q)")
    )
    assert evidence.status is EvidenceStatus.VALID
    assert evidence.char_start is None


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
    evidence = validator.validate(Evidence(artifact="cmd/main.go", start_line=1, quote="{"))
    assert evidence.status is EvidenceStatus.EMPTY


# --------------------------------------------------------------------------- #
# вердикт целиком
# --------------------------------------------------------------------------- #

def test_verdict_without_evidence_goes_to_human(validator):
    verdict = validator.validate_verdict(
        CriterionVerdict(criterion_id="c1", score=2, confidence=0.9, verdict="всё хорошо"),
        go_rubric().criterion("c1"),
    )
    assert verdict.needs_human_attention
    assert "не привела ни одной проверяемой цитаты" in verdict.attention_reason


def test_verdict_with_fabricated_evidence_goes_to_human(validator):
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c1", score=2, confidence=0.9, verdict="есть слои",
            evidence=[Evidence(artifact="cmd/main.go", start_line=5,
                               quote="здесь настроен внедрённый через wire контейнер")],
        ),
        go_rubric().criterion("c1"),
    )
    assert verdict.needs_human_attention


def test_low_confidence_goes_to_human(validator):
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c3", score=2, confidence=0.4, verdict="вроде есть",
            evidence=[Evidence(artifact="cmd/main.go", start_line=16,
                               quote='log.Println("Shutting down service-courier")')],
        ),
        go_rubric().criterion("c3"),
    )
    assert verdict.needs_human_attention
    assert "низкая уверенность" in verdict.attention_reason


def test_score_above_maximum_is_clamped_and_flagged(validator):
    verdict = validator.validate_verdict(
        CriterionVerdict(
            criterion_id="c1", score=99, confidence=0.9, verdict="отлично",
            evidence=[Evidence(artifact="cmd/main.go", start_line=10,
                               quote='r.Get("/ping", handlePing)')],
        ),
        go_rubric().criterion("c1"),
    )
    assert verdict.score == 2
    assert verdict.needs_human_attention


def test_normalize_drops_whitespace_and_case():
    assert normalize("  Log.Println( \n  x )") == "log.println(x)"


def test_normalize_does_not_make_everything_match():
    """Пробелы игнорируем, но последовательность символов должна совпадать."""
    assert normalize("func main") not in normalize("func handlePing")
