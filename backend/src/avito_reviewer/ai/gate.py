"""Format Gate — проверки, которые не стоят ни одного токена.

Самое неожиданное из разбора условий: они сами содержат жёсткие формальные
требования, проверяемые кодом. «Лог должен писать `Shutting down
service-courier`», «порт переопределяется флагом `--port`», «код разделён на
`cmd/` и `internal/`» — всё это ревьюер проверяет глазами в первую минуту, и
всё это детерминированно.

Отсюда обязательный шаг **перед** любым обращением к модели:

    тексты сдачи → GATE ──┬─ passed  → анализы
                          └─ warning → анализы, и непройденное названо в карточке

Гейт больше не останавливает разбор. Раньше непройденная проверка уровня
`blocking` возвращала работу ревьюеру, не запуская модель: дословной строки в
логе нет — и студент не получал ни слова о том, что у него сделано хорошо.
Экономия на токенах не стоит того: формальное требование чаще не выполнено по
недосмотру, а отзыв нужен и такой работе. Проверки остались все до одной, и
результат каждой уходит в модель фактом и ревьюеру строкой — меняется только
то, что за ними следует.

Две причины, почему это важнее, чем кажется:

1. **Совпадение с реальностью.** Мы не изобретаем процесс, а повторяем то, что
   ревьюер делает руками.
3. **Точность.** «18 тест-кейсов вместо 21» — детерминированный факт. Отдавать
   его модели значит превращать точный ответ в вероятностный, поэтому факты
   гейта подмешиваются в промпт как уже установленные.

**Чего не видели — то не «отсутствует».** Проверка на присутствие строки в
файле, доступном фрагментом, не может дать отрицательный ответ: мы смотрели не
весь файл. Такая проверка помечается неубедительной и никогда не блокирует
сдачу — она уходит человеку.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from avito_reviewer.ingest import Revision, SubmissionBundle

from .content import ArtifactText
from .rubric import FormatCheck, Rubric

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3


class GateStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    """Что-то не сошлось. Разбор всё равно идёт: гейт сообщает, а не запрещает.

    Значения `blocked` больше нет. Оно означало «модель не запускается», и
    непройденное дословное требование стоило студенту всего отзыва целиком.
    """


class CheckOutcome(BaseModel):
    check: str
    level: Literal["blocking", "warning", "info"]
    label: str
    passed: bool
    inconclusive: bool = False
    """Ответить по доступным данным нельзя.

    Проверка на отсутствие в файле, который показан фрагментом, — не провал, а
    отсутствие ответа. Такая проверка не блокирует сдачу и уходит человеку.
    """
    detail: str = ""
    locations: list[str] = Field(default_factory=list)

    @property
    def blocks(self) -> bool:
        return self.level == "blocking" and not self.passed and not self.inconclusive


@dataclass(frozen=True, slots=True)
class GateContext:
    """Сдача, по которой отвечают проверки.

    Тексты и карта путей собраны заранее — их читает почти каждая проверка;
    бандл нужен тем, чей ответ лежит не в файлах, а в самой сдаче.
    """

    bundle: SubmissionBundle
    texts: list[ArtifactText]
    paths: set[str]


class GateReport(BaseModel):
    status: GateStatus = GateStatus.PASSED
    outcomes: list[CheckOutcome] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    """Установленные факты для промпта ревью — модель их не пересчитывает."""

    @property
    def failures(self) -> list[CheckOutcome]:
        return [o for o in self.outcomes if not o.passed and not o.inconclusive]

    @property
    def unresolved(self) -> list[CheckOutcome]:
        return [o for o in self.outcomes if o.inconclusive]


def run(
    bundle: SubmissionBundle, texts: list[ArtifactText], rubric: Rubric
) -> GateReport:
    """Прогнать формальные проверки рубрики. Ни одного обращения к модели."""
    report = GateReport()
    if not rubric.format_gate:
        return report

    context = GateContext(bundle=bundle, texts=texts, paths=_known_paths(bundle, texts))
    for check in rubric.format_gate:
        outcome = _run_check(check, context)
        if outcome is not None:
            report.outcomes.append(outcome)

    report.status = _status(report.outcomes)
    report.facts = [_fact(o) for o in report.outcomes]
    log.info(
        "gate %s — %s: провалено %d, без ответа %d",
        rubric.assignment_id,
        report.status.value,
        len(report.failures),
        len(report.unresolved),
    )
    return report


# --------------------------------------------------------------------------- #

def _known_paths(bundle: SubmissionBundle, texts: list[ArtifactText]) -> set[str]:
    """Все пути сдачи, а не только затронутые изменением.

    Требование «код разделён на cmd/ и internal/» относится к репозиторию, а не
    к диффу: каталог мог появиться в прошлой сдаче и остаться на месте. Карта
    репозитория для того и собирается.
    """
    paths = {text.path for text in texts} | {a.path for a in bundle.artifacts}
    if bundle.repo:
        paths |= set(bundle.repo.files)
    return paths


def _status(outcomes: list[CheckOutcome]) -> GateStatus:
    # `o.blocks` осталось у проверки как её уровень важности — по нему ревьюер
    # отличает дословное требование условия от пожелания. Статусом отчёта оно
    # больше не управляет.
    if any(o.blocks for o in outcomes):
        return GateStatus.WARNING
    if any(
        (not o.passed and o.level != "info") or (o.inconclusive and o.level == "blocking")
        for o in outcomes
    ):
        return GateStatus.WARNING
    return GateStatus.PASSED


def _run_check(check: FormatCheck, context: GateContext) -> CheckOutcome | None:
    handler = _HANDLERS.get(check.check)
    if handler is None:
        # Молча пропасть проверка не имеет права: рубрика несёт требования
        # условия, и часть из них исполняется только другим каналом сдачи —
        # шрифт и число страниц живут в Google Docs, а не в git. Пропавшая
        # блокирующая проверка означала бы работу, прошедшую гейт без проверки.
        log.warning("gate: проверка %r не реализована — уходит человеку", check.check)
        return CheckOutcome(
            check=check.check,
            level=check.level,
            label=_label(check, check.check),
            passed=False,
            inconclusive=True,
            detail="проверка не реализована для этого источника сдачи — проверьте вручную",
        )
    return handler(check, context)


def _label(check: FormatCheck, fallback: str) -> str:
    return str(check.params.get("label") or check.note or fallback)


def _required_paths(check: FormatCheck, context: GateContext) -> CheckOutcome:
    paths = context.paths
    wanted = [str(p) for p in check.params.get("paths", [])]
    missing = [p for p in wanted if not _path_present(p, paths)]
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=_label(check, "Обязательные пути: " + ", ".join(wanted)),
        passed=not missing,
        detail=(
            "на месте: " + ", ".join(wanted)
            if not missing
            else "не найдено: " + ", ".join(missing)
        ),
        locations=[p for p in wanted if _path_present(p, paths)],
    )


def _forbidden_paths(check: FormatCheck, context: GateContext) -> CheckOutcome:
    paths = context.paths
    wanted = [str(p) for p in check.params.get("paths", [])]
    pattern = check.params.get("pattern")
    found = [p for p in wanted if _path_present(p, paths)]
    if pattern:
        matcher = re.compile(str(pattern))
        found += sorted(p for p in paths if matcher.search(p))
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=_label(check, "Запрещённые пути"),
        passed=not found,
        detail="не найдено — как и требуется" if not found else "найдено: " + ", ".join(found),
        locations=found,
    )


def _path_present(wanted: str, paths: set[str]) -> bool:
    """`cmd/` — это каталог: достаточно любого файла под ним."""
    if wanted.endswith("/"):
        return any(path.startswith(wanted) for path in paths)
    return wanted in paths or any(path.endswith("/" + wanted) for path in paths)


def _candidates(check: FormatCheck, texts: list[ArtifactText]) -> list[ArtifactText]:
    suffixes = tuple(str(s) for s in check.params.get("in", []))
    if not suffixes:
        return list(texts)
    return [text for text in texts if text.path.endswith(suffixes)]


def _code_contains(check: FormatCheck, context: GateContext) -> CheckOutcome:
    pattern = re.compile(str(check.params.get("pattern", "")))
    expected = str(check.params.get("expected") or check.params.get("pattern", ""))
    candidates = _candidates(check, context.texts)

    hits = [where for text in candidates if (where := _find(text, pattern))]
    if hits:
        return CheckOutcome(
            check=check.check,
            level=check.level,
            label=_label(check, expected),
            passed=True,
            detail=f"найдено: {expected}",
            locations=hits,
        )

    # Отсутствие в куске файла — не отсутствие в работе.
    fragments = [text.path for text in candidates if text.partial]
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=_label(check, expected),
        passed=False,
        inconclusive=bool(fragments),
        detail=(
            f"не найдено: {expected}"
            if not fragments
            else f"не найдено в доступной части; показаны фрагментами: {', '.join(fragments)}"
        ),
    )


def _code_absent(check: FormatCheck, context: GateContext) -> CheckOutcome:
    pattern = re.compile(str(check.params.get("pattern", "")))
    label = _label(check, "Запрещённый фрагмент")
    hits = [where for text in _candidates(check, context.texts) if (where := _find(text, pattern))]
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=label,
        passed=not hits,
        detail="не найдено — как и требуется" if not hits else "найдено: " + ", ".join(hits),
        locations=hits,
    )


def _find(text: ArtifactText, pattern: re.Pattern[str]) -> str | None:
    """Первое совпадение с номером строки в координатах полной версии файла."""
    for number, line in zip(text.line_numbers, text.lines, strict=True):
        if pattern.search(line):
            return f"{text.path}:{number}"
    return None


def _token_budget(check: FormatCheck, context: GateContext) -> CheckOutcome:
    limit = int(check.params.get("max_tokens", 0) or 0)
    estimate = sum(len(text.text) for text in context.texts) // CHARS_PER_TOKEN
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=_label(check, "Объём работы"),
        passed=not limit or estimate <= limit,
        detail=f"около {estimate} токенов" + (f" при лимите {limit}" if limit else ""),
    )


def _revision_history(check: FormatCheck, context: GateContext) -> CheckOutcome:
    """История изменений сдачи. В git-канале это коммиты pull request'а.

    Требование пришло из условия, написанного про Google Docs («оформите работу
    с доступом на редактирование: должна быть видна история изменений, иначе
    работа принята не будет»), и в git оно исполнимо: коммиты лежат в бандле.
    Отвечать на него здесь — сознательная переинтерпретация требования во
    втором канале, а не закрытие пробела.

    Пустая история — не «истории нет», а «источник её не отдал»: pull request
    без коммитов не бывает. Поэтому такой ответ уходит человеку и не блокирует
    сдачу. Судить о том, что история из одного коммита выглядит подозрительно,
    — работа форензики детектора, а не гейта.
    """
    revisions = context.bundle.revisions
    label = _label(check, "Видна история изменений")
    if not revisions:
        return CheckOutcome(
            check=check.check,
            level=check.level,
            label=label,
            passed=False,
            inconclusive=True,
            detail="история сдачи не пришла от источника — проверьте вручную",
        )
    return CheckOutcome(
        check=check.check,
        level=check.level,
        label=label,
        passed=True,
        detail=f"коммитов: {len(revisions)}, {_span(revisions)}",
    )


def _span(revisions: list[Revision]) -> str:
    days = sorted(revision.authored_at.date().isoformat() for revision in revisions)
    return days[0] if days[0] == days[-1] else f"{days[0]} — {days[-1]}"


_HANDLERS = {
    "required_paths": _required_paths,
    "forbidden_paths": _forbidden_paths,
    "code_contains": _code_contains,
    "code_absent": _code_absent,
    "token_budget": _token_budget,
    "revision_history_visible": _revision_history,
}


def _fact(outcome: CheckOutcome) -> str:
    mark = "✓" if outcome.passed else ("?" if outcome.inconclusive else "✗")
    where = f" ({', '.join(outcome.locations[:3])})" if outcome.locations else ""
    return f"{mark} {outcome.label}: {outcome.detail}{where}"
