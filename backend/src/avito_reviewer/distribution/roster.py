"""Каталог ревьюеров: добавить куратора — значит положить рядом ещё один JSON.

Тот же приём, что и с рубриками (`ai/rubric.py`), и по той же причине: состав
курса меняется чаще, чем код, и правка состава не должна быть выкаткой. Базы
нет, поэтому каталог — файлы; когда база появится, поменяется этот модуль, а не
солвер, который получает ревьюеров списком на вход.

Один сломанный файл не роняет каталог: он пропускается с записью в лог.
Отсутствующий каталог тоже переживается — приложение обязано подниматься без
данных, иначе первый же запуск на чистой машине выглядит как поломка.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .schema import Reviewer

log = logging.getLogger(__name__)

ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


class ReviewerRejected(ValueError):
    """Карточка не годится в каталог: список поломок в `problems`."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def load_reviewer(path: str | Path) -> Reviewer:
    return Reviewer.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_reviewer(reviewer: Reviewer) -> list[str]:
    """Что проверяет код перед тем, как пустить карточку в распределение."""
    problems: list[str] = []
    if not ID_PATTERN.match(reviewer.id):
        problems.append(
            f"идентификатор {reviewer.id!r} не годится в имя файла: "
            "латиница, цифры, точка, дефис, подчёркивание"
        )
    if not reviewer.name.strip():
        problems.append("у ревьюера нет имени — координатор не поймёт, кому отдали работу")
    if reviewer.capacity_minutes < 0:
        problems.append(f"ёмкость отрицательная: {reviewer.capacity_minutes}")
    if reviewer.median_minutes_per_work < 0:
        problems.append(f"медиана отрицательная: {reviewer.median_minutes_per_work}")
    if reviewer.max_items is not None and reviewer.max_items <= 0:
        problems.append(
            f"max_items={reviewer.max_items}: чтобы вывести ревьюера из распределения, "
            "снимите active, а не ставьте ноль работ"
        )
    return problems


class ReviewerStore:
    """Ревьюеры, разложенные по файлам каталога."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._reviewers: dict[str, Reviewer] = {}
        self.reload()

    def reload(self) -> None:
        self._reviewers = {}
        if not self.directory.is_dir():
            log.warning("reviewers: %s is not a directory — no reviewers loaded", self.directory)
            return
        for path in sorted(self.directory.glob("*.json")):
            try:
                reviewer = load_reviewer(path)
            except (ValueError, TypeError, OSError) as exc:
                log.warning("reviewers: skipping %s — %s", path.name, exc)
                continue
            problems = validate_reviewer(reviewer)
            if problems:
                log.warning("reviewers: skipping %s — %s", path.name, "; ".join(problems))
                continue
            self._reviewers[reviewer.id] = reviewer
        log.info("reviewers: loaded %d from %s", len(self._reviewers), self.directory)

    def get(self, reviewer_id: str) -> Reviewer | None:
        return self._reviewers.get(reviewer_id)

    def all(self) -> list[Reviewer]:
        return [self._reviewers[key] for key in sorted(self._reviewers)]

    @property
    def ids(self) -> list[str]:
        return sorted(self._reviewers)
