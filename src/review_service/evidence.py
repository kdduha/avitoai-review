"""Программная проверка цитат.

Главный анти-галлюцинационный механизм всей системы. Модель утверждает, что
в `order.go` строках 44–58 написано вот это — мы идём и смотрим. Не совпало:
вердикт помечается как требующий человека и не подаётся ревьюеру как готовый.

Сверка нестрогая по пробелам и регистру, но строгая по существу. Модель
регулярно переносит строки иначе, чем в файле, склеивает отступы или
пересказывает фрагмент вместо цитирования — первое нас устраивает, второе нет.
Поэтому сравниваем нормализованные строки и разрешаем небольшой сдвиг по
номерам: попасть в нужный фрагмент важнее, чем попасть в точную строку.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .schema import CriterionVerdict, Evidence, EvidenceStatus

LINE_TOLERANCE = 3      # на столько строк модель может промахнуться
MIN_QUOTE_CHARS = 12    # слишком короткая цитата ничего не подтверждает


def normalize(text: str) -> str:
    """Убрать пробелы целиком и опустить регистр.

    Схлопывания повторов до одного пробела оказалось мало: модель ставит
    пробелы внутри скобок, разносит аргументы по строкам, меняет отступы —
    и `log.Println(  "x"  )` перестаёт совпадать с `log.Println("x")`.
    Удаляем пробелы полностью: содержательная разница от этого не теряется,
    а выдуманную цитату это по-прежнему не пропустит — последовательность
    символов должна совпасть буквально, и минимальная длина цитаты
    защищает от случайных совпадений на границах слов.
    """
    return re.sub(r"\s+", "", text).lower()


class EvidenceValidator:
    def __init__(self, artifacts: Iterable[Any]) -> None:
        self._by_path: dict[str, Any] = {}
        for artifact in artifacts:
            self._by_path[artifact.path.lower()] = artifact
            # модель часто указывает только имя файла
            self._by_path.setdefault(artifact.path.split("/")[-1].lower(), artifact)

    # ------------------------------------------------------------------ #

    def _find_artifact(self, path: str) -> Any | None:
        key = path.strip().lower()
        if key in self._by_path:
            return self._by_path[key]
        # модель могла дописать префикс каталога, которого нет в сдаче
        for known_path, artifact in self._by_path.items():
            if known_path.endswith(key) or key.endswith(known_path):
                return artifact
        return None

    def validate(self, evidence: Evidence) -> Evidence:
        if not evidence.quote or len(evidence.quote.strip()) < MIN_QUOTE_CHARS:
            evidence.status = EvidenceStatus.EMPTY
            evidence.note = "цитата пустая или слишком короткая, чтобы что-то подтверждать"
            return evidence

        artifact = self._find_artifact(evidence.artifact)
        if artifact is None:
            evidence.status = EvidenceStatus.NO_SUCH_ARTIFACT
            evidence.note = f"в сдаче нет файла {evidence.artifact}"
            return evidence

        evidence.artifact_id = getattr(artifact, "id", None)
        evidence.artifact = artifact.path

        lines = artifact.text.splitlines()
        needle = normalize(evidence.quote)

        # 1. Точное попадание в указанные строки, с допуском на промах.
        if evidence.start_line:
            start = max(1, evidence.start_line - LINE_TOLERANCE)
            end = min(len(lines), (evidence.end_line or evidence.start_line) + LINE_TOLERANCE)
            window = normalize("\n".join(lines[start - 1 : end]))
            if needle in window:
                evidence.status = EvidenceStatus.VALID
                evidence.char_start, evidence.char_end = _offsets(artifact.text, evidence.quote)
                return evidence

        # 2. Фрагмент есть, но не там, где указано. Это всё ещё галлюцинация
        #    адреса, но не содержания: чиним координаты и говорим об этом.
        whole = normalize(artifact.text)
        if needle in whole:
            found_line = _locate_line(lines, needle)
            evidence.note = (
                f"цитата найдена, но в строке {found_line}, а не {evidence.start_line}"
                if found_line else "цитата найдена в файле, но не в указанных строках"
            )
            if found_line:
                span = (evidence.end_line or evidence.start_line or found_line) - (
                    evidence.start_line or found_line
                )
                evidence.start_line, evidence.end_line = found_line, found_line + max(0, span)
                evidence.status = EvidenceStatus.VALID
                evidence.char_start, evidence.char_end = _offsets(artifact.text, evidence.quote)
            else:
                evidence.status = EvidenceStatus.WRONG_LOCATION
            return evidence

        evidence.status = EvidenceStatus.WRONG_LOCATION
        evidence.note = "такого текста в файле нет — вердикт не подтверждён"
        return evidence

    # ------------------------------------------------------------------ #

    def validate_verdict(self, verdict: CriterionVerdict, criterion: Any | None) -> CriterionVerdict:
        """Проверить цитаты вердикта и решить, можно ли его показывать как готовый."""
        verdict.evidence = [self.validate(e) for e in verdict.evidence]

        requires_evidence = bool(getattr(criterion, "evidence_required", True)) if criterion else True
        if requires_evidence and not verdict.valid_evidence:
            verdict.needs_human_attention = True
            reasons = {e.note for e in verdict.evidence if e.note}
            verdict.attention_reason = (
                "вердикт не подтверждён цитатой: " + "; ".join(sorted(reasons))
                if reasons else "модель не привела ни одной проверяемой цитаты"
            )

        # Низкая уверенность — тоже повод показать вердикт человеку, а не
        # выдавать его за готовый.
        if verdict.confidence < 0.6 and not verdict.needs_human_attention:
            verdict.needs_human_attention = True
            verdict.attention_reason = f"низкая уверенность модели ({verdict.confidence:.2f})"

        # Балл вне границ критерия — признак того, что модель не поняла шкалу.
        if criterion is not None:
            if verdict.score > criterion.max_score:
                verdict.needs_human_attention = True
                verdict.attention_reason = (
                    f"модель выставила {verdict.score:g} при максимуме {criterion.max_score:g}"
                )
                verdict.score = criterion.max_score
            if verdict.score < 0:
                verdict.score = 0.0

        return verdict


# --------------------------------------------------------------------------- #

def _offsets(text: str, quote: str) -> tuple[int | None, int | None]:
    """Смещения цитаты в тексте артефакта — для подсветки в интерфейсе."""
    index = text.find(quote.strip())
    if index == -1:
        stripped = quote.strip().split("\n")[0].strip()
        index = text.find(stripped) if stripped else -1
        if index == -1:
            return None, None
        return index, index + len(stripped)
    return index, index + len(quote.strip())


def _locate_line(lines: list[str], needle: str) -> int | None:
    """Первая строка окна, в котором встречается нормализованная цитата."""
    for size in (1, 2, 3, 5, 8):
        for i in range(len(lines) - size + 1):
            if needle in normalize("\n".join(lines[i : i + size])):
                return i + 1
    return None
