"""Рубрика как данные.

Промпт генерируется из этой структуры, а не пишется руками под каждое
задание: добавить курс значит добавить JSON. Схема должна вмещать все формы,
в которых условия приходят на самом деле, — таблицу с баллами, N вопросов по
фиксированному баллу, чек-лист без баллов вовсе, требования к формату со
штрафами.

Три поля появились из разбора реальных условий и объясняют, почему нельзя
свести оценку к сумме:

* `min_score_for_pass` — в системном дизайне провал по обязательному критерию
  не компенсируется набранным на остальных;
* `step` — баллы дробные, и округлять надо по правилу задания;
* `checks[]` — «проверочные пункты для преподавателя» из условия; модель
  отвечает по каждому отдельно, и разброс между прогонами резко падает.

Заполняет рубрику методист (в перспективе — Rubric Compiler с подтверждением
человеком). Здесь только схема, разбор и реестр.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

log = logging.getLogger(__name__)


class Scale(BaseModel):
    """Шкала задания: максимум, порог зачёта и шаг округления."""

    total_max: float
    pass_threshold: float | None = None
    step: float = 1.0

    def round_to_step(self, value: float) -> float:
        if self.step <= 0:
            return value
        return round(round(value / self.step) * self.step, 4)


class LatePolicy(BaseModel):
    """Штраф за просрочку — правило из условия, а не наша выдумка.

    «Досдача в течение 1 дня после дедлайна — −1 балл; позже — 0 баллов»
    ложится сюда как `grace_days=1, penalty_per_grace_day=1, after_grace=zero`.
    """

    grace_days: int = 0
    penalty_per_grace_day: float = Field(
        default=0.0,
        validation_alias=AliasChoices("penalty_per_grace_day", "penalty_per_grace"),
    )
    after_grace: Literal["zero", "continue"] = Field(
        default="zero", validation_alias=AliasChoices("after_grace", "after")
    )

    def apply(
        self, score: float, submitted_at: datetime | None, deadline_at: datetime | None
    ) -> tuple[float, str]:
        if not submitted_at or not deadline_at:
            return score, "сдано в срок"

        submitted, deadline = _aligned(submitted_at, deadline_at)
        if submitted <= deadline:
            return score, "сдано в срок"

        days = max(1, -(-(submitted - deadline) // timedelta(days=1)))
        if days <= self.grace_days:
            penalty = self.penalty_per_grace_day * days
            return max(0.0, score - penalty), f"просрочка {days} дн., штраф −{penalty:g}"
        if self.after_grace == "zero":
            return 0.0, f"просрочка {days} дн. — 0 баллов"
        penalty = self.penalty_per_grace_day * days
        return max(0.0, score - penalty), f"просрочка {days} дн., штраф −{penalty:g}"


def _aligned(left: datetime, right: datetime) -> tuple[datetime, datetime]:
    """Привести срок и время сдачи к сравнимому виду.

    `submitted_at` приходит от провайдера и всегда со смещением, а `deadline_at`
    — из тела запроса, где клиент может прислать «2026-02-09T23:59» без зоны.
    Сравнение таких дат роняет запрос целиком, поэтому наивную дату читаем как
    UTC: ошибиться на смещение лучше, чем отдать 500 на штатном вводе.
    """
    if (left.tzinfo is None) == (right.tzinfo is None):
        return left, right
    return (
        left if left.tzinfo else left.replace(tzinfo=UTC),
        right if right.tzinfo else right.replace(tzinfo=UTC),
    )


class FormatCheck(BaseModel):
    """Формальное требование из условия — проверяется кодом, без единого токена.

    Format Gate ещё не построен; рубрики уже несут его правила, потому что
    вынимать их из условия надо один раз вместе с критериями, а не потом.
    """

    check: str
    level: Literal["blocking", "warning", "info"] = "warning"
    """`blocking` — к ревьюеру без прогона модели; `warning` — флаг в карточке;
    `info` — факт в контекст ревью-агента, чтобы он не пересчитывал его сам."""
    params: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class Criterion(BaseModel):
    id: str
    title: str
    max_score: float
    min_score_for_pass: float | None = None
    weight: float = 1.0
    description: str = ""
    checks: list[str] = Field(default_factory=list)
    anchors: dict[str, str] = Field(default_factory=dict)
    evidence_required: bool = True
    auto_verifiable: bool = False
    """Проверяется детерминированно (Format Gate, smoke-тесты), а не моделью."""
    ai_sensitive: bool = False
    """Критерий про самостоятельность: сигнал детектора здесь показывается первым."""

    @field_validator("anchors", mode="before")
    @classmethod
    def _stringify_keys(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): str(text) for key, text in value.items()}
        return value


class Rubric(BaseModel):
    assignment_id: str
    title: str = ""
    course: str = ""
    stage: str | None = None
    source_note: str = ""
    ai_policy: str = "declare_required"

    scale: Scale
    late_policy: LatePolicy = Field(default_factory=LatePolicy)
    format_gate: list[FormatCheck] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)

    @field_validator("format_gate", mode="before")
    @classmethod
    def _normalize_gate(cls, value: Any) -> Any:
        """Принять и плоский список, и группировку по уровню из архитектуры."""
        if isinstance(value, dict):
            return [
                {**check, "level": level}
                for level in ("blocking", "warning", "info")
                for check in value.get(level, [])
                if isinstance(check, dict)
            ]
        return value

    def criterion(self, criterion_id: str) -> Criterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)

    @property
    def ai_sensitive_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.ai_sensitive]


ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def validate_rubric(rubric: Rubric) -> list[str]:
    """Что не так с рубрикой. Пустой список — можно принимать.

    Проверяет код, а не модель, и проверяет то, что ломает подсчёт балла на
    каждой работе потока: рубрика действует до конца курса, и арифметическая
    ошибка в ней стоит дороже любой ошибки в одном черновике.
    """
    problems: list[str] = []

    if not ID_PATTERN.match(rubric.assignment_id):
        problems.append(
            f"идентификатор {rubric.assignment_id!r} не годится для имени файла: "
            f"латиница, цифры, точка, дефис и подчёркивание"
        )
    if not rubric.criteria:
        problems.append("в рубрике нет ни одного критерия")

    ids = [c.id for c in rubric.criteria]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append("повторяющиеся идентификаторы критериев: " + ", ".join(duplicates))

    if rubric.scale.total_max <= 0:
        problems.append("максимальный балл должен быть больше нуля")
    if rubric.scale.step < 0:
        problems.append("шаг шкалы не может быть отрицательным")

    threshold = rubric.scale.pass_threshold
    if threshold is not None and threshold > rubric.scale.total_max:
        problems.append(
            f"порог зачёта {threshold:g} выше максимума {rubric.scale.total_max:g} — "
            f"зачёт недостижим"
        )

    for criterion in rubric.criteria:
        if criterion.max_score <= 0:
            problems.append(f"{criterion.id}: максимум критерия должен быть больше нуля")
        minimum = criterion.min_score_for_pass
        if minimum is not None and minimum > criterion.max_score:
            problems.append(
                f"{criterion.id}: обязательный минимум {minimum:g} выше максимума "
                f"{criterion.max_score:g} — критерий провален всегда"
            )

    # Сумма может не совпадать с максимумом: у критериев бывают веса. А вот
    # недостижимый максимум — это уже поломка шкалы.
    reachable = round(sum(c.max_score * (c.weight or 1.0) for c in rubric.criteria), 4)
    if rubric.criteria and reachable < rubric.scale.total_max:
        problems.append(
            f"максимум {rubric.scale.total_max:g} недостижим: по всем критериям "
            f"с весами набирается {reachable:g}"
        )
    return problems


def load_rubric(path: str | Path) -> Rubric:
    return Rubric.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


class RubricRejected(ValueError):
    """Рубрика не прошла проверку и в каталог не попала."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class RubricExists(ValueError):
    """Рубрика с таким идентификатором уже есть."""

    def __init__(self, assignment_id: str) -> None:
        super().__init__(f"рубрика {assignment_id!r} уже существует")
        self.assignment_id = assignment_id


class RubricStore:
    """Рубрики из каталога JSON-файлов.

    Пока рубрики не переехали в базу и админку, каталог — и есть источник
    правды: `rubrics/<assignment>.json`, ключ — `assignment_id`.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._rubrics: dict[str, Rubric] = {}
        self.reload()

    def reload(self) -> None:
        self._rubrics = {}
        if not self.directory.is_dir():
            log.warning("rubrics: %s is not a directory — no rubrics loaded", self.directory)
            return
        for path in sorted(self.directory.glob("*.json")):
            try:
                rubric = load_rubric(path)
            except (ValueError, TypeError, OSError) as exc:
                log.warning("rubrics: skipping %s — %s", path.name, exc)
                continue
            self._rubrics[rubric.assignment_id] = rubric
        log.info("rubrics: loaded %d from %s", len(self._rubrics), self.directory)

    def get(self, assignment_id: str) -> Rubric | None:
        return self._rubrics.get(assignment_id)

    def save(self, rubric: Rubric, *, overwrite: bool = False) -> Path:
        """Положить подтверждённую рубрику в каталог.

        Молча переписать существующую нельзя: по ней уже могли быть проверены
        работы, и подмена задним числом делает их баллы необъяснимыми.
        """
        problems = validate_rubric(rubric)
        if problems:
            raise RubricRejected(problems)

        path = self.directory / f"{rubric.assignment_id}.json"
        if path.exists() and not overwrite:
            raise RubricExists(rubric.assignment_id)

        self.directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            rubric.model_dump_json(indent=2, exclude_defaults=False), encoding="utf-8"
        )
        self._rubrics[rubric.assignment_id] = rubric
        log.info("rubrics: saved %s to %s", rubric.assignment_id, path)
        return path

    def delete(self, assignment_id: str) -> None:
        """Remove a rubric from the catalogue. Submissions already scored against
        it keep meaning what they meant — `Submission.rubric_snapshot` froze the
        rubric at scoring time, so deleting the file here does not touch them.
        """
        if assignment_id not in self._rubrics:
            raise KeyError(assignment_id)
        path = self.directory / f"{assignment_id}.json"
        path.unlink(missing_ok=True)
        del self._rubrics[assignment_id]
        log.info("rubrics: deleted %s", assignment_id)

    @property
    def ids(self) -> list[str]:
        return sorted(self._rubrics)
