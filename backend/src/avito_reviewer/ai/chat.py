"""Итеративный чат ревьюера с моделью (архитектура §6.3).

Модель здесь снова не оценивает работу заново — она читает то, что уже есть
(черновик, файлы, рубрику) через тот же набор тулов, что описан в
архитектуре, и либо отвечает, либо просит очередной тул. `propose_review_patch`
не меняет черновик сама: она возвращает `ProposedPatch`, а применяет его
`PATCH /submissions/{id}/review` — тот же путь, что и ручная правка, с тем же
пересчётом и той же записью в `review_revisions`. Раз патч предложен,
цикл останавливается: решение — предложить ещё раз или применить — за
ревьюером, не за следующей итерацией агента.

Каждый шаг (вызов тула, его результат, финальный ответ) — отдельный
`ChatStep`: роутер персистит и стримит их по одному, а не ждёт весь цикл.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.detection import DetectionReport
from avito_reviewer.ai.llm import (
    DataClass,
    Identity,
    LLMError,
    LLMUnavailable,
    PrivacyGateway,
    StructuredError,
    TaskKind,
    complete_json,
)
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.rubric import Rubric

log = logging.getLogger(__name__)

MAX_STEPS = 4
SEARCH_HITS = 15
FILE_CHARS = 4000

_TOOLS = ("get_file", "get_diff", "get_criterion", "search_submission", "propose_review_patch")

SYSTEM_PROMPT = """Ты помогаешь ревьюеру разобраться в уже готовом черновике \
проверки — не оцениваешь работу заново, а объясняешь то, что уже посчитано, \
и по запросу предлагаешь точечную правку.

Правила:
1. Любое утверждение о содержимом работы подкрепляй тулом — get_file или \
search_submission. Не пересказывай файл по памяти из более раннего шага, \
если ревьюер спрашивает про конкретные строки: перечитай их.
2. Файл, отмеченный ФРАГМЕНТОМ в get_file, показан не целиком. Отсутствие \
чего-то в показанном куске не значит отсутствие в работе — скажи это прямо, \
а не промолчи.
3. propose_review_patch предлагает, не применяет. После него — не вызывай \
больше тулов, вернись с action="tool" один раз и остановись: применение \
решает ревьюер, не следующий шаг цикла.
4. Если вопрос не требует тула — просто отвечай.

Отвечай строго валидным JSON по этой схеме, без markdown-обрамления:

{"action": "tool", "tool": "get_file", "args": {"path": "...", "start_line": 1, "end_line": 40}, "reply": "что делаешь и зачем, одна фраза"}
{"action": "tool", "tool": "get_diff", "args": {"path": "..."}, "reply": "..."}
{"action": "tool", "tool": "get_criterion", "args": {"criterion_id": "c2"}, "reply": "..."}
{"action": "tool", "tool": "search_submission", "args": {"query": "..."}, "reply": "..."}
{"action": "tool", "tool": "propose_review_patch",
 "args": {"criterion_id": "c2", "score": 11, "verdict": "новый текст вердикта", "reason": "почему меняешь"},
 "reply": "короткое объяснение предложения для ревьюера"}
{"action": "reply", "reply": "финальный ответ ревьюеру"}

`args` для каждого тула — ровно те поля, что в примере; необязательные можно \
опустить. `score`/`verdict` в propose_review_patch — тоже необязательные, но \
хотя бы одно должно быть указано."""


class ProposedPatch(BaseModel):
    criterion_id: str
    score: float | None = None
    verdict: str | None = None
    student_feedback: str | None = None


class AgentStep(BaseModel):
    """Один структурированный ход модели: вызвать тул или ответить."""

    action: Literal["tool", "reply"]
    tool: Literal[
        "get_file", "get_diff", "get_criterion", "search_submission", "propose_review_patch"
    ] | None = None
    args: dict = Field(default_factory=dict)
    reply: str = ""


class ChatStep(BaseModel):
    """Один шаг транскрипта — то, что роутер персистит и стримит."""

    kind: Literal["tool", "reply"]
    tool_name: str | None = None
    content: str
    proposed_patch: ProposedPatch | None = None


def _render_criterion(rubric: Rubric, criterion_id: str, draft: ReviewDraft) -> str:
    criterion = rubric.criterion(criterion_id)
    if criterion is None:
        return f"критерия {criterion_id!r} нет в рубрике"
    lines = [f"[{criterion.id}] {criterion.title} — максимум {criterion.max_score:g}"]
    if criterion.min_score_for_pass is not None:
        lines.append(f"обязательный минимум: {criterion.min_score_for_pass:g}")
    if criterion.checks:
        lines.append("проверочные пункты: " + "; ".join(criterion.checks))
    if criterion.anchors:
        lines.append("якоря: " + "; ".join(f"{k} — {v}" for k, v in criterion.anchors.items()))

    # Цитаты вердикта — здесь, а не отдельным тулом: спросив про критерий,
    # спрашивают и про то, на чём стоит балл. Отдельный тул означал бы лишний
    # шаг цикла ради данных, которые уже лежат в этом же черновике.
    verdict = next((v for v in draft.verdicts if v.criterion_id == criterion_id), None)
    if verdict is not None:
        lines.append(f"выставленный балл: {verdict.score:g} — {verdict.verdict}")
        valid = verdict.valid_evidence
        if valid:
            lines.append("цитаты, на которых стоит балл:")
            lines.extend(
                f"  {e.artifact}"
                + (f":{e.start_line}" if e.start_line is not None else "")
                + f" — {e.quote}"
                for e in valid
            )
        # Несошедшаяся цитата важнее сошедшейся: именно её ревьюер и проверяет.
        unmatched = [e for e in verdict.evidence if not e.is_valid]
        if unmatched:
            lines.append(
                "цитаты, которые не сошлись с текстом файла (вывод по ним ненадёжен): "
                + "; ".join(f"{e.artifact} [{e.status.value}]" for e in unmatched)
            )
    return "\n".join(lines)


def _render_gate(draft: ReviewDraft) -> str:
    """Формальные проверки — установленные факты, а не мнение модели.

    Без них агент пересказывает по файлам то, что гейт уже проверил кодом, и
    иногда расходится с ним: «тестов нет» при пройденной проверке на тесты
    читается ревьюером как ошибка разбора, а это ошибка контекста.
    """
    if draft.gate is None and not draft.gate_facts:
        return ""
    lines = []
    if draft.gate is not None:
        lines.append(f"Format Gate: {draft.gate.status.value}.")
        if draft.gate.status.value == "blocked":
            lines.append("Работа не принята по формату — модель разбор не проводила.")
    if draft.gate_facts:
        lines.append("Установлено проверками (это факты, не переспрашивайте файлы):")
        lines.extend(f"  {fact}" for fact in draft.gate_facts)
    return "\n".join(lines)


def _render_detection(report: DetectionReport | None) -> str:
    """Сводка сигнала ГенИИ — рекомендательная, и так и подписана.

    Агент обязан знать, что отчёт существует и что он значит: без этого на
    вопрос «почему работа помечена» он отвечает догадкой. Спаны не
    разворачиваются: их место в панели детектора, а не в реплике.
    """
    if report is None or not report.signals:
        return ""
    return (
        f"Сигнал ГенИИ: {report.label} ({report.overall_score:.2f}). "
        f"Вывод рекомендательный: на балл не влияет, решение принимает ревьюер. "
        f"Подозрительных фрагментов: {len(report.spans)}."
    )


def _render_draft(draft: ReviewDraft) -> str:
    rows = [f"[{v.criterion_id}] балл {v.score:g}: {v.verdict}" for v in draft.verdicts]
    return (
        f"Текущий итог: {draft.score:g} из {draft.max_score:g} "
        f"({'зачёт' if draft.passed else 'ниже порога'}).\n" + "\n".join(rows)
    )


def _call_tool(
    tool: str,
    args: dict,
    *,
    texts: dict[str, ArtifactText],
    rubric: Rubric,
    diffs: dict[str, str],
    draft: ReviewDraft,
) -> str:
    if tool == "get_file":
        path = str(args.get("path", ""))
        text = texts.get(path)
        if text is None:
            return f"файл {path!r} не входит в разбор этой сдачи; доступны: " + ", ".join(list(texts)[:20])
        start, end = args.get("start_line"), args.get("end_line")
        if start and end:
            window = text.window(int(start), int(end))
            return window or "в доступной части файла этих строк нет"
        note = " (ФРАГМЕНТ — показана не вся работа)" if text.partial else ""
        return f"{path}{note}\n{text.text[:FILE_CHARS]}"

    if tool == "get_diff":
        wanted = args.get("path")
        if wanted:
            return diffs.get(str(wanted), f"диффа для {wanted!r} нет")
        if not diffs:
            return "диффов нет"
        return "\n\n".join(f"--- {p} ---\n{d}" for p, d in list(diffs.items())[:5])

    if tool == "get_criterion":
        return _render_criterion(rubric, str(args.get("criterion_id", "")), draft)

    if tool == "search_submission":
        query = str(args.get("query", "")).lower().strip()
        if not query:
            return "пустой запрос"
        hits: list[str] = []
        for path, text in texts.items():
            for line, number in zip(text.lines, text.line_numbers, strict=True):
                if query in line.lower():
                    hits.append(f"{path}:{number}: {line.strip()}")
                    if len(hits) >= SEARCH_HITS:
                        break
            if len(hits) >= SEARCH_HITS:
                break
        return "\n".join(hits) if hits else "совпадений не найдено"

    return f"неизвестный тул {tool!r}"


def run_chat(
    gateway: PrivacyGateway,
    *,
    rubric: Rubric,
    draft: ReviewDraft,
    texts: list[ArtifactText],
    diffs: dict[str, str],
    history: list[dict[str, str]],
    message: str,
    detection: DetectionReport | None = None,
    identities: Sequence[Identity] = (),
    max_steps: int = MAX_STEPS,
) -> list[ChatStep]:
    """Провести один ход разговора, выполняя тулы, которые попросит модель.

    `history` — прежние реплики этой же сдачи (`role`/`content`), без
    служебных сообщений тулов: агент каждый раз начинает с чистого системного
    промпта плюс сведённый контекст, а не тащит весь прошлый внутренний диалог.
    """
    texts_by_path = {text.path: text for text in texts}
    context = "\n\n".join(
        part
        for part in (
            f"Рубрика: {rubric.title or rubric.assignment_id}.\n{_render_draft(draft)}",
            _render_gate(draft),
            _render_detection(detection),
            f"Файлы в разборе: {', '.join(sorted(texts_by_path)) or 'нет'}."
            + (
                f"\nПоказаны фрагментом (вывод «этого в работе нет» по ним ненадёжен): "
                f"{', '.join(draft.partial_artifacts)}."
                if draft.partial_artifacts
                else ""
            ),
        )
        if part
    )
    messages: list[dict[str, str]] = (
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": context}, *history, {"role": "user", "content": message}]
    )

    steps: list[ChatStep] = []
    for _ in range(max_steps):
        try:
            step, _result = complete_json(
                gateway,
                messages,
                AgentStep,
                task=TaskKind.CHAT,
                data_class=DataClass.CONTAINS_PD,
                identities=identities,
                max_tokens=1200,
            )
        except (StructuredError, LLMError, LLMUnavailable) as exc:
            log.warning("chat: модель не ответила: %s", exc)
            steps.append(ChatStep(kind="reply", content="Модель не ответила, попробуйте ещё раз."))
            return steps

        if step.action == "reply" or step.tool is None:
            steps.append(ChatStep(kind="reply", content=step.reply or "Не удалось сформулировать ответ."))
            return steps

        if step.tool == "propose_review_patch":
            try:
                patch = ProposedPatch.model_validate({"criterion_id": "", **step.args})
            except Exception:  # noqa: BLE001 — модель могла вернуть что угодно в args
                patch = None
            if patch is None or not patch.criterion_id:
                steps.append(ChatStep(kind="reply", content="Не удалось разобрать предложенную правку."))
                return steps
            steps.append(
                ChatStep(
                    kind="tool", tool_name=step.tool,
                    content=step.reply or "Предлагаю правку черновика.",
                    proposed_patch=patch,
                )
            )
            return steps

        if step.tool not in _TOOLS:
            steps.append(ChatStep(kind="reply", content=f"неизвестный тул {step.tool!r}"))
            return steps

        result_text = _call_tool(
            step.tool, step.args, texts=texts_by_path, rubric=rubric, diffs=diffs, draft=draft
        )
        steps.append(ChatStep(kind="tool", tool_name=step.tool, content=result_text))
        messages.append({"role": "assistant", "content": step.model_dump_json(exclude_none=True)})
        messages.append({"role": "user", "content": f"[результат {step.tool}]\n{result_text}"})

    steps.append(ChatStep(kind="reply", content="Слишком много шагов подряд — уточните вопрос."))
    return steps
