"""Рубрика как данные.

Условия приходят в четырёх разных формах, и схема обязана вместить их все,
иначе «добавить курс = добавить JSON» перестаёт быть правдой.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from factories import NOW

from avito_reviewer.ai.rubric import (
    LatePolicy,
    Rubric,
    RubricExists,
    RubricRejected,
    RubricStore,
    load_rubric,
    validate_rubric,
)

RUBRICS = Path(__file__).resolve().parents[1] / "rubrics"

MINIMAL = {
    "assignment_id": "x",
    "scale": {"total_max": 6, "pass_threshold": 4, "step": 0.5},
}


def test_the_shipped_rubric_loads():
    rubric = load_rubric(RUBRICS / "go-task1.json")
    assert rubric.assignment_id == "go-task1"
    assert rubric.scale.step == 0.5
    assert rubric.criteria and rubric.criterion("c1") is not None
    assert rubric.format_gate


def test_checks_and_anchors_survive_the_round_trip():
    """Их модель получает дословно — это якоря для цитат и для баллов."""
    criterion = load_rubric(RUBRICS / "go-task1.json").criterion("c1")
    assert criterion.checks
    assert set(criterion.anchors) >= {"0", "2"}


def test_gate_levels_from_the_real_rubric_are_accepted():
    levels = {check.level for check in load_rubric(RUBRICS / "go-task1.json").format_gate}
    assert levels <= {"blocking", "warning", "info"}


def test_gate_grouped_by_level_is_accepted_too():
    """В архитектуре гейт записан объектом, в рубрике — списком. Оба варианта живые."""
    rubric = Rubric.model_validate({
        **MINIMAL,
        "format_gate": {
            "blocking": [{"check": "revision_history_visible"}],
            "warning": [{"check": "max_pages", "params": {"value": 3}}],
        },
    })
    assert [(c.check, c.level) for c in rubric.format_gate] == [
        ("revision_history_visible", "blocking"),
        ("max_pages", "warning"),
    ]


def test_late_policy_accepts_both_spellings():
    rubric = Rubric.model_validate({
        **MINIMAL,
        "late_policy": {"grace_days": 1, "penalty_per_grace": 1, "after": "zero"},
    })
    assert rubric.late_policy.penalty_per_grace_day == 1
    assert rubric.late_policy.after_grace == "zero"


def test_numeric_anchor_keys_become_strings():
    rubric = Rubric.model_validate({
        **MINIMAL,
        "criteria": [{"id": "c1", "title": "t", "max_score": 2, "anchors": {0: "нет", 2: "есть"}}],
    })
    assert rubric.criterion("c1").anchors == {"0": "нет", "2": "есть"}


@pytest.mark.parametrize(
    "days,expected",
    [(0, 6.0), (1, 5.0), (3, 0.0)],
)
def test_late_policy_matches_the_wording_of_the_assignment(days, expected):
    """«Досдача в течение 1 дня — −1 балл; позже — 0 баллов»."""
    policy = LatePolicy(grace_days=1, penalty_per_grace_day=1, after_grace="zero")
    score, _ = policy.apply(6.0, NOW + timedelta(days=days), NOW)
    assert score == expected


def test_rounding_follows_the_step_of_the_scale():
    rubric = Rubric.model_validate(MINIMAL)
    assert rubric.scale.round_to_step(3.9) == 4.0
    assert rubric.scale.round_to_step(3.7) == 3.5


# --------------------------------------------------------------------------- #
# каталог
# --------------------------------------------------------------------------- #

def test_store_loads_the_directory():
    store = RubricStore(RUBRICS)
    assert "go-task1" in store.ids
    assert store.get("go-task1") is not None
    assert store.get("нет такой") is None


def test_a_broken_file_does_not_take_down_the_catalogue(tmp_path):
    """Одна кривая рубрика не должна лишать ревьюера всех остальных."""
    (tmp_path / "good.json").write_text(json.dumps(MINIMAL), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{не json", encoding="utf-8")
    (tmp_path / "incomplete.json").write_text('{"assignment_id": "y"}', encoding="utf-8")

    assert RubricStore(tmp_path).ids == ["x"]


def test_a_missing_directory_is_survivable(tmp_path):
    assert RubricStore(tmp_path / "nope").ids == []


def test_naive_deadline_does_not_crash_the_endpoint():
    """`deadline_at` приходит из тела запроса и может приехать без зоны."""
    policy = LatePolicy(grace_days=1, penalty_per_grace_day=1)
    aware = NOW
    naive = NOW.replace(tzinfo=None)

    assert policy.apply(6.0, aware, naive) == (6.0, "сдано в срок")
    score, note = policy.apply(6.0, aware + timedelta(hours=3), naive)
    assert score == 5.0 and "штраф" in note


def test_malformed_gate_entry_is_skipped_not_fatal(tmp_path):
    """Одна кривая запись не должна валить разбор рубрики TypeError'ом."""
    (tmp_path / "r.json").write_text(
        json.dumps(
            {
                "assignment_id": "r",
                "scale": {"total_max": 1},
                "format_gate": {"blocking": ["нет тестов", {"check": "required_paths"}]},
            }
        ),
        encoding="utf-8",
    )
    store = RubricStore(tmp_path)
    assert [c.check for c in store.get("r").format_gate] == ["required_paths"]


# --------------------------------------------------------------------------- #
# проверка перед принятием
# --------------------------------------------------------------------------- #

def rubric_with(**overrides) -> Rubric:
    payload = {
        "assignment_id": "lab1",
        "scale": {"total_max": 4, "pass_threshold": 3, "step": 0.5},
        "criteria": [
            {"id": "c1", "title": "Раз", "max_score": 2},
            {"id": "c2", "title": "Два", "max_score": 2},
        ],
    }
    payload.update(overrides)
    return Rubric.model_validate(payload)


def test_a_working_rubric_passes():
    assert validate_rubric(rubric_with()) == []


def test_unreachable_threshold_is_rejected():
    """Порог выше максимума — зачёт не получит никто и никогда."""
    problems = validate_rubric(rubric_with(scale={"total_max": 4, "pass_threshold": 10}))
    assert any("зачёт недостижим" in p for p in problems)


def test_unreachable_maximum_is_rejected():
    """Шкала на 10 при критериях на 4 — балл не сойдётся ни на одной работе."""
    problems = validate_rubric(rubric_with(scale={"total_max": 10}))
    assert any("недостижим" in p for p in problems)


def test_minimum_above_maximum_is_rejected():
    """Такой критерий провален всегда, что бы студент ни сдал."""
    problems = validate_rubric(rubric_with(criteria=[
        {"id": "c1", "title": "Раз", "max_score": 2, "min_score_for_pass": 5},
        {"id": "c2", "title": "Два", "max_score": 2},
    ]))
    assert any("провален всегда" in p for p in problems)


def test_duplicate_criteria_ids_are_rejected():
    problems = validate_rubric(rubric_with(criteria=[
        {"id": "c1", "title": "Раз", "max_score": 2},
        {"id": "c1", "title": "Два", "max_score": 2},
    ]))
    assert any("повторяющиеся идентификаторы" in p for p in problems)


def test_id_unfit_for_a_filename_is_rejected():
    assert any("не годится для имени файла" in p for p in validate_rubric(rubric_with(assignment_id="../etc/passwd")))


def test_empty_rubric_is_rejected():
    assert any("ни одного критерия" in p for p in validate_rubric(rubric_with(criteria=[])))


def test_weights_let_the_sum_differ_from_the_maximum():
    """Сумма критериев не обязана равняться максимуму: у критериев бывают веса."""
    weighted = rubric_with(
        scale={"total_max": 8},
        criteria=[
            {"id": "c1", "title": "Раз", "max_score": 2, "weight": 2},
            {"id": "c2", "title": "Два", "max_score": 2, "weight": 2},
        ],
    )
    assert validate_rubric(weighted) == []


# --------------------------------------------------------------------------- #
# запись в каталог
# --------------------------------------------------------------------------- #

def test_confirmed_rubric_lands_in_the_catalogue(tmp_path):
    store = RubricStore(tmp_path)
    path = store.save(rubric_with())

    assert path.exists()
    assert store.get("lab1") is not None
    assert RubricStore(tmp_path).ids == ["lab1"]  # переживает перезапуск


def test_existing_rubric_is_not_overwritten_silently(tmp_path):
    """По старой рубрике могли быть выставлены баллы: подмена делает их необъяснимыми."""
    store = RubricStore(tmp_path)
    store.save(rubric_with())

    with pytest.raises(RubricExists):
        store.save(rubric_with(title="другая"))

    store.save(rubric_with(title="другая"), overwrite=True)
    assert store.get("lab1").title == "другая"


def test_broken_rubric_never_reaches_the_catalogue(tmp_path):
    store = RubricStore(tmp_path)
    with pytest.raises(RubricRejected) as exc:
        store.save(rubric_with(scale={"total_max": 4, "pass_threshold": 99}))

    assert exc.value.problems
    assert list(tmp_path.iterdir()) == []
