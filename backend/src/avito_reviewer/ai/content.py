"""Текст артефакта там, где его может не быть.

`SubmissionBundle` не обещает полного текста файла: ingest инлайнит `excerpt`
только в пределах бюджета, крупное едет diff-only, тело живёт за `content_ref`.
Здесь из трёх источников получается один объект для ревью и детектора.

Главное — флаг `partial`. Вердикт «в работе нет обработки ошибок», сделанный по
одному диффу, некорректен, поэтому неполнота не прячется:

* в промпте такой файл помечен, и системная инструкция запрещает выводы об
  отсутствии чего-либо;
* валидатор цитат говорит «не найдено в доступной части», а не «такого текста
  нет»;
* стилометрия и перплексия такие файлы пропускают: по обрывкам строк статистика
  даёт и ложную ровность, и ложную рваность;
* список неполных файлов уходит в черновик и в ограничения детектора.

Файл, добавленный этой сдачей, — исключение: его дифф и есть весь файл.
Проверяем это по покрытию строк и размеру из дерева, а не по статусу: дифф
крупного файла GitHub может и обрезать.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import nbformat

from avito_reviewer.config import ContentConfig
from avito_reviewer.ingest import Artifact, ArtifactRole, ChangeStatus, SubmissionBundle
from avito_reviewer.ingest.diff import head_lines_from_patch

log = logging.getLogger(__name__)

EXCERPT = "excerpt"
FETCHED = "fetched"
DIFF = "diff"

# Дифф считается полным текстом файла, если покрывает строки с первой подряд и
# набирает почти весь размер из дерева. Допуск — на перевод строки и кодировку.
_SIZE_TOLERANCE = 0.9


class ContentResolver(Protocol):
    """Тот, кто умеет достать тело файла по `Artifact.content_ref`.

    Схемы ссылок знает только ingest — здесь мы не разбираем `content_ref` и не
    догадываемся о провайдере. `IngestService` подходит под этот протокол.
    """

    async def fetch_content(self, content_ref: str) -> str | None: ...


@dataclass
class ArtifactText:
    """Артефакт вместе с тем текстом, который до него удалось достать.

    `line_numbers[i]` — номер строки `lines[i]` в полной версии файла. У
    целого файла это 1..N, у фрагмента — с пропусками, и именно поэтому
    координаты цитат считаются через него, а не через позицию в списке.
    """

    path: str
    role: ArtifactRole
    status: ChangeStatus
    lang: str | None
    lines: list[str]
    line_numbers: list[int]
    changed: set[int] = field(default_factory=set)
    partial: bool = False
    origin: str = DIFF
    text: str = ""

    def __post_init__(self) -> None:
        self.text = "\n".join(self.lines)

    @property
    def head_line_count(self) -> int:
        return self.line_numbers[-1] if self.line_numbers else 0

    def index_of(self, head_line: int) -> int | None:
        """Позиция строки `head_line` в доступном тексте, если она вообще доступна."""
        try:
            return self.line_numbers.index(head_line)
        except ValueError:
            return None

    def window(self, start: int, end: int) -> str:
        """Доступные строки в диапазоне номеров полной версии файла."""
        return "\n".join(
            line
            for line, number in zip(self.lines, self.line_numbers, strict=True)
            if start <= number <= end
        )

    def changed_summary(self) -> str:
        """Строки этой сдачи одной строкой: «1–48, 120»."""
        if not self.changed:
            return ""
        ordered = sorted(self.changed)
        spans: list[tuple[int, int]] = [(ordered[0], ordered[0])]
        for number in ordered[1:]:
            if number == spans[-1][1] + 1:
                spans[-1] = (spans[-1][0], number)
            else:
                spans.append((number, number))
        return ", ".join(f"{a}–{b}" if a != b else str(a) for a, b in spans)


_NOTEBOOK_OUTPUT_CHARS = 800


def strip_notebook(raw: str) -> str | None:
    """`.ipynb` JSON → code, markdown and truncated text output. `None` if it
    does not even parse as a notebook (then the caller falls back to the raw
    JSON, same as any other unrecognised text).

    A saved output cell is the single biggest source of wasted tokens in this
    pipeline: one real "хорошее решение" from the LLM course repo ran ~116k
    tokens raw and ~14k stripped, purely from base64 plot images and long
    stdout dumps sitting in `outputs`. None of that is the student's
    argument — it is the notebook remembering what a prior run printed.
    """
    try:
        notebook = nbformat.reads(raw, as_version=4)
    except Exception:
        return None

    parts: list[str] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            parts.append(cell.get("source", ""))
        elif cell_type == "code":
            parts.append(f"```python\n{cell.get('source', '')}\n```")
            for output in cell.get("outputs", []) or []:
                rendered = _notebook_output_text(output, index)
                if rendered:
                    parts.append(rendered)
        # 'raw' cells: export boilerplate, not the student's work — skipped.
    return "\n\n".join(part for part in parts if part)


def _notebook_output_text(output: dict[str, Any], cell_index: int) -> str | None:
    kind = output.get("output_type")
    if kind == "stream":
        return _truncate_output("".join(output.get("text", "")))
    if kind == "error":
        return f"[error: {output.get('ename', '')}: {output.get('evalue', '')}]"
    if kind in ("execute_result", "display_data"):
        data = output.get("data", {}) or {}
        if any(mime.startswith("image/") for mime in data):
            # Плейсхолдер, а не описание: содержание графика по имени переменной
            # не угадываем.
            return f"[plot: cell {cell_index}]"
        if "text/plain" in data:
            return _truncate_output("".join(data["text/plain"]))
    return None


def _truncate_output(text: str) -> str:
    text = text.strip()
    if len(text) <= _NOTEBOOK_OUTPUT_CHARS:
        return text
    kept = text[:_NOTEBOOK_OUTPUT_CHARS]
    return f"{kept}… [вывод обрезан, ещё {len(text) - _NOTEBOOK_OUTPUT_CHARS} симв.]"


def from_artifact(artifact: Artifact, body: str | None = None) -> ArtifactText | None:
    """Собрать текст артефакта из тела, `excerpt` или диффа. `None` — показывать нечего."""
    changed = {
        number
        for span in artifact.changed_ranges
        for number in range(span.start, span.end + 1)
    }
    full = body if body is not None else artifact.excerpt
    origin = FETCHED if body is not None else EXCERPT

    if full is not None:
        if artifact.lang == "jupyter":
            stripped = strip_notebook(full)
            if stripped is not None:
                full = stripped
                # Строки диффа — в координатах сырого JSON: после переформатирования
                # они ни на что не указывают, а неверный диапазон хуже пустого.
                changed = set()
        lines = full.splitlines()
        return ArtifactText(
            path=artifact.path,
            role=artifact.role,
            status=artifact.status,
            lang=artifact.lang,
            lines=lines,
            line_numbers=list(range(1, len(lines) + 1)),
            changed=changed,
            partial=False,
            origin=origin,
        )

    if not artifact.diff:
        return None

    numbered = head_lines_from_patch(artifact.diff)
    if not numbered:
        return None

    ordered = sorted(numbered)
    lines = [numbered[number] for number in ordered]
    return ArtifactText(
        path=artifact.path,
        role=artifact.role,
        status=artifact.status,
        lang=artifact.lang,
        lines=lines,
        line_numbers=ordered,
        changed=changed,
        partial=not _covers_whole_file(artifact, ordered, lines),
        origin=DIFF,
    )


def _covers_whole_file(artifact: Artifact, ordered: list[int], lines: list[str]) -> bool:
    if ordered != list(range(1, len(ordered) + 1)):
        return False
    if artifact.size_bytes <= 0:
        # Размера из дерева нет — считать дифф полным файлом не на чем.
        return False
    return len("\n".join(lines).encode()) >= artifact.size_bytes * _SIZE_TOLERANCE


async def build_texts(
    bundle: SubmissionBundle,
    resolver: ContentResolver | None = None,
    *,
    config: ContentConfig | None = None,
) -> list[ArtifactText]:
    """Тексты артефактов сдачи, с дозагрузкой тел в пределах бюджета.

    Тела тянутся до входа в синхронный слой и параллельно: так резолвер
    остаётся асинхронным, а ревью и детектор получают готовые тексты и не ходят
    в сеть посреди разбора. Что не влезло в бюджет — приезжает диффом и честно
    помечается фрагментом.
    """
    config = config or ContentConfig()
    candidates = [
        artifact
        for artifact in bundle.artifacts
        if artifact.role is not ArtifactRole.NOISE
        and not artifact.is_binary
        and artifact.status is not ChangeStatus.REMOVED
    ]

    bodies = await _fetch_bodies(candidates, resolver, config)
    texts = [
        text
        for artifact in candidates
        if (text := from_artifact(artifact, bodies.get(artifact.path))) is not None
    ]

    partial = [text.path for text in texts if text.partial]
    if partial:
        log.info(
            "content: %d of %d artifacts available in part only: %s",
            len(partial),
            len(texts),
            ", ".join(partial[:5]),
        )
    return texts


async def _fetch_bodies(
    artifacts: list[Artifact],
    resolver: ContentResolver | None,
    config: ContentConfig,
) -> dict[str, str]:
    if resolver is None:
        return {}

    wanted = [
        artifact
        for artifact in artifacts
        if artifact.excerpt is None
        and artifact.content_ref is not None
        and 0 < artifact.size_bytes <= config.max_file_bytes
    ]
    # По возрастанию размера: за тот же бюджет получаем больше целых файлов.
    wanted.sort(key=lambda artifact: artifact.size_bytes)
    wanted = wanted[: config.max_files]
    if not wanted:
        return {}

    results = await asyncio.gather(
        *(resolver.fetch_content(artifact.content_ref or "") for artifact in wanted),
        return_exceptions=True,
    )

    bodies: dict[str, str] = {}
    for artifact, result in zip(wanted, results, strict=False):
        if isinstance(result, BaseException):
            log.warning("content: fetch failed for %s: %s", artifact.path, result)
            continue
        if result is not None:
            bodies[artifact.path] = result
    return bodies


def solution_texts(texts: list[ArtifactText]) -> list[ArtifactText]:
    """То, что оценивается: работа студента без обвязки и без шума."""
    return [text for text in texts if text.role is ArtifactRole.SOLUTION]


def gradable_texts(texts: list[ArtifactText]) -> list[ArtifactText]:
    """Работа плюс приложенные подтверждения — то, что идёт в ревью."""
    return [
        text
        for text in texts
        if text.role in (ArtifactRole.SOLUTION, ArtifactRole.EVIDENCE)
    ]
