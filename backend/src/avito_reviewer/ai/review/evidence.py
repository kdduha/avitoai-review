"""Программная проверка цитат.

Главный анти-галлюцинационный механизм системы. Модель утверждает, что в
`order.go` строках 44–58 написано вот это — мы идём и смотрим. Не совпало:
вердикт помечается требующим человека и не подаётся ревьюеру как готовый.

Сверка нестрогая по пробелам и регистру, но строгая по существу: модель
регулярно переносит строки иначе, чем в файле, — это допустимо; пересказ вместо
цитаты — нет. Небольшой сдвиг по номерам разрешён: попасть в нужный фрагмент
важнее, чем в точную строку.

У файлов, доступных фрагментом, отдельный статус и другая формулировка: «нет в
файле» про файл, который мы видели наполовину, — обвинение на основании
собственной неосведомлённости.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.rubric import Criterion

from .schema import CriterionVerdict, Evidence, EvidenceStatus

LINE_TOLERANCE = 3      # на столько строк модель может промахнуться
MIN_QUOTE_CHARS = 12    # слишком короткая цитата ничего не подтверждает
WINDOW_SIZES = (1, 2, 3, 5, 8)
MIN_FRAGMENT_CHARS = 8  # осколок склеенной цитаты короче этого ничего не значит

_ELLIPSIS = re.compile(r"\s*(?:\.\s*\.\s*\.|…)\s*")


def fragments(quote: str) -> list[str]:
    """Разбить цитату, склеенную многоточием, на куски.

    Модель регулярно отвечает «строка А ... строка Б», выкидывая середину.
    Целиком такой текст в файле не найдётся никогда, и вердикт помечался
    непроверяемым, хотя каждый кусок в файле есть. Проверяем куски.
    """
    parts = [normalize(p) for p in _ELLIPSIS.split(quote) if p.strip()]
    return [p for p in parts if len(p) >= MIN_FRAGMENT_CHARS]


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
    def __init__(self, texts: Iterable[ArtifactText]) -> None:
        self._by_path: dict[str, ArtifactText] = {}
        for text in texts:
            self._by_path[text.path.lower()] = text
            # модель часто указывает только имя файла
            self._by_path.setdefault(text.path.split("/")[-1].lower(), text)


    def _find(self, path: str) -> ArtifactText | None:
        key = path.strip().lower()
        if key in self._by_path:
            return self._by_path[key]
        # модель могла дописать префикс каталога, которого нет в сдаче
        for known_path, text in self._by_path.items():
            if known_path.endswith(key) or key.endswith(known_path):
                return text
        return None

    def validate(self, evidence: Evidence) -> Evidence:
        if not evidence.quote or len(evidence.quote.strip()) < MIN_QUOTE_CHARS:
            evidence.status = EvidenceStatus.EMPTY
            evidence.note = "цитата пустая или слишком короткая, чтобы что-то подтверждать"
            return evidence

        artifact = self._find(evidence.artifact)
        if artifact is None:
            evidence.status = EvidenceStatus.NO_SUCH_ARTIFACT
            evidence.note = f"в сдаче нет файла {evidence.artifact}"
            return evidence

        evidence.artifact = artifact.path
        needle = normalize(evidence.quote)

        # 1. Точное попадание в указанные строки, с допуском на промах.
        if evidence.start_line:
            start = evidence.start_line - LINE_TOLERANCE
            end = (evidence.end_line or evidence.start_line) + LINE_TOLERANCE
            if needle in normalize(artifact.window(start, end)):
                return self._accept(evidence, artifact)

        # 2. Фрагмент есть, но не там: галлюцинация адреса, а не содержания —
        #    чиним координаты и говорим об этом.
        if needle in normalize(artifact.text):
            found_line = _locate_line(artifact, needle)
            evidence.note = (
                f"цитата найдена, но в строке {found_line}, а не {evidence.start_line}"
                if found_line
                else "цитата найдена в файле, но не в указанных строках"
            )
            if found_line:
                span = (evidence.end_line or evidence.start_line or found_line) - (
                    evidence.start_line or found_line
                )
                evidence.start_line = found_line
                evidence.end_line = found_line + max(0, span)
                return self._accept(evidence, artifact, note=evidence.note)
            evidence.status = EvidenceStatus.WRONG_LOCATION
            return evidence

        # 3. Цитата склеена многоточием: целиком её в файле нет и быть не
        #    может, но каждый кусок обязан найтись. Это не галлюцинация, а
        #    другой формат ответа.
        pieces = fragments(evidence.quote)
        if len(pieces) > 1:
            whole = normalize(artifact.text)
            missing = [p for p in pieces if p not in whole]
            if not missing:
                return self._accept(
                    evidence,
                    artifact,
                    note=f"цитата собрана из {len(pieces)} фрагментов — каждый найден в файле",
                )
            evidence.status = (
                EvidenceStatus.NOT_IN_AVAILABLE_PART
                if artifact.partial
                else EvidenceStatus.WRONG_LOCATION
            )
            evidence.note = (
                f"из {len(pieces)} фрагментов цитаты не найдено {len(missing)}"
            )
            return evidence

        # 4. Не нашли. Что именно это значит — зависит от того, весь ли файл мы видели.
        if artifact.partial:
            evidence.status = EvidenceStatus.NOT_IN_AVAILABLE_PART
            evidence.note = (
                "цитаты нет в доступной части файла — файл показан фрагментом, "
                "проверьте по исходнику"
            )
            return evidence

        evidence.status = EvidenceStatus.WRONG_LOCATION
        evidence.note = "такого текста в файле нет — вердикт не подтверждён"
        return evidence

    def _accept(self, evidence: Evidence, artifact: ArtifactText, note: str = "") -> Evidence:
        evidence.status = EvidenceStatus.VALID
        evidence.note = note
        # Смещения в символах имеют смысл только для целого файла: в тексте из
        # диффа они указывали бы в наш кусок.
        if not artifact.partial:
            evidence.char_start, evidence.char_end = _offsets(artifact.text, evidence.quote)
        return evidence


    def validate_verdict(
        self, verdict: CriterionVerdict, criterion: Criterion | None
    ) -> CriterionVerdict:
        """Проверить цитаты вердикта и решить, можно ли его показывать как готовый."""
        verdict.evidence = [self.validate(e) for e in verdict.evidence]

        requires_evidence = criterion.evidence_required if criterion else True
        if requires_evidence and not verdict.valid_evidence:
            verdict.needs_human_attention = True
            reasons = {e.note for e in verdict.evidence if e.note}
            verdict.attention_reason = (
                "вердикт не подтверждён цитатой: " + "; ".join(sorted(reasons))
                if reasons
                else "модель не привела ни одной проверяемой цитаты"
            )

        # Низкая уверенность — повод показать вердикт человеку, а не выдать готовым.
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


def _locate_line(artifact: ArtifactText, needle: str) -> int | None:
    """Номер строки в полной версии файла, с которой начинается найденная цитата."""
    for size in WINDOW_SIZES:
        for i in range(len(artifact.lines) - size + 1):
            if needle in normalize("\n".join(artifact.lines[i : i + size])):
                return artifact.line_numbers[i]
    return None
