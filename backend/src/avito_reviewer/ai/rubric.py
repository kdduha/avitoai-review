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
from datetime import datetime, timedelta
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
        if not submitted_at or not deadline_at or submitted_at <= deadline_at:
            return score, "сдано в срок"

        days = max(1, -(-(submitted_at - deadline_at) // timedelta(days=1)))
        if days <= self.grace_days:
            penalty = self.penalty_per_grace_day * days
            return max(0.0, score - penalty), f"просрочка {days} дн., штраф −{penalty:g}"
        if self.after_grace == "zero":
            return 0.0, f"просрочка {days} дн. — 0 баллов"
        penalty = self.penalty_per_grace_day * days
        return max(0.0, score - penalty), f"просрочка {days} дн., штраф −{penalty:g}"


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
            ]
        return value

    def criterion(self, criterion_id: str) -> Criterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)

    @property
    def ai_sensitive_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.ai_sensitive]


def load_rubric(path: str | Path) -> Rubric:
    return Rubric.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


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
            except (ValueError, OSError) as exc:
                log.warning("rubrics: skipping %s — %s", path.name, exc)
                continue
            self._rubrics[rubric.assignment_id] = rubric
        log.info("rubrics: loaded %d from %s", len(self._rubrics), self.directory)

    def get(self, assignment_id: str) -> Rubric | None:
        return self._rubrics.get(assignment_id)

    @property
    def ids(self) -> list[str]:
        return sorted(self._rubrics)
