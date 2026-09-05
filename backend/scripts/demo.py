#!/usr/bin/env python3
"""Сквозной прогон ревью и детектора — без сети и без ключа.

    uv run python scripts/demo.py review
    uv run python scripts/demo.py detect

По умолчанию берётся записанный бандл `scripts/fixtures/go-task1-pr42.json` —
ровно та форма, что отдаёт ingest на настоящем PR, включая крупный файл без
инлайненного тела. Реальные работы и живой прогон:

    git clone https://github.com/ai-talent-hub-avito/homework_examples.git
    uv run python scripts/demo.py --repo "homework_examples/GO/Хорошее решение 1-3" review

    uv run python scripts/demo.py --link https://github.com/owner/repo/pull/1 review
    AI_LLM__PROVIDER=openrouter AI_LLM__API_KEY=... uv run python scripts/demo.py review

Без ключа модель не вызывается: ответы собираются из настоящих строк работы,
поэтому валидатор цитат подтверждает их так же, как подтвердил бы живой ответ.
Одна цитата намеренно выдумана — на прогоне видно, как её отбраковывают.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_bundle

from avito_reviewer.ai import AIService, load_rubric
from avito_reviewer.ai.content import ArtifactText, solution_texts
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.ai.review import aggregate, explain
from avito_reviewer.ai.rubric import Rubric
from avito_reviewer.config import AIConfig, IngestConfig
from avito_reviewer.ingest import IngestContext, SubmissionBundle, SubmissionSource

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts" / "fixtures" / "go-task1-pr42.json"
RUBRIC = ROOT / "rubrics" / "go-task1.json"

FABRICATED = "здесь реализована ретрай-логика с экспоненциальной задержкой"


def rule(title: str) -> None:
    print(f"\n{title}\n" + "─" * 78)


async def load_bundle(args) -> SubmissionBundle:
    if args.repo:
        return local_bundle.load(args.repo)
    if args.link is None:
        return SubmissionBundle.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    from avito_reviewer.ingest import IngestService

    service = IngestService(IngestConfig())
    try:
        return await service.ingest(args.link, SubmissionSource.GITHUB_PR, context=IngestContext())
    finally:
        await service.aclose()


def canned(texts: list[ArtifactText], rubric: Rubric, batch_size: int) -> list[str]:
    """Правдоподобные ответы модели, собранные из настоящих строк работы.

    Нужны, чтобы демо без ключа проходило весь путь целиком, включая сверку
    цитат. Номера строк берутся из полной версии файла — той же системы
    координат, в которой отвечает живая модель.
    """
    quotes: list[tuple[str, int, str]] = [
        (text.path, number, line.strip())
        for text in texts
        for number, line in zip(text.line_numbers, text.lines, strict=False)
        if len(line.strip()) > 25 and not line.strip().startswith(("//", "#", "import"))
    ]

    criteria = rubric.criteria
    batches = [criteria[i : i + batch_size] for i in range(0, len(criteria), batch_size)]
    responses: list[str] = []
    index, spoiled = 0, False

    for batch in batches:
        verdicts = []
        for criterion in batch:
            path, line, quote = (
                quotes[index % len(quotes)] if quotes else ("README.md", 1, "нет содержимого")
            )
            index += 7
            if not spoiled and len(batch) > 1:
                # Одна выдуманная цитата на прогон: видно, как её отбрасывают.
                quote, spoiled = FABRICATED, True

            verdicts.append({
                "criterion_id": criterion.id,
                "score": round(criterion.max_score * 0.75, 1),
                "confidence": 0.82,
                "verdict": f"Требования критерия «{criterion.title}» выполнены частично.",
                "evidence": [
                    {"artifact": path, "start_line": line, "end_line": line, "quote": quote}
                ],
                "student_feedback": "Основа собрана аккуратно, давай докрутим детали.",
                "improvement_hint": "Добавить обработку граничных случаев.",
                "needs_human_attention": False,
                "attention_reason": "",
            })
        responses.append(json.dumps({"verdicts": verdicts}, ensure_ascii=False))
    return responses


def describe(texts: list[ArtifactText]) -> None:
    """Что слой вообще увидел. Роль важна: оценивается только `solution`."""
    print(f"{'файл':<32} {'роль':<9} {'откуда':<9} {'строк':>6}  изменено в этой сдаче")
    for text in texts:
        mark = "ФРАГМЕНТ" if text.partial else text.origin
        print(
            f"{text.path:<32} {text.role.value:<9} {mark:<9} "
            f"{len(text.lines):>6}  {text.changed_summary()[:24]}"
        )


# --------------------------------------------------------------------------- #

async def cmd_review(args) -> int:
    rubric = load_rubric(RUBRIC)
    bundle = await load_bundle(args)

    config = AIConfig()
    config.review.batch_size = args.batch
    live = config.llm.provider != "fake"

    probe = AIService(config, gateway=fake_gateway([])[0])
    texts = await probe.prepare(bundle)

    ai = (
        AIService(config)
        if live
        else AIService(
            config,
            gateway=fake_gateway(canned(solution_texts(texts), rubric, args.batch))[0],
        )
    )

    rule(f"СДАЧА · {bundle.origin_url}")
    describe(texts)
    if not live:
        print(
            "\nПровайдер fake: ответы собраны из настоящих строк работы, модель не "
            "вызывается.\nОдна цитата намеренно выдумана — видно отбраковку. "
            "Живой прогон: AI_LLM__PROVIDER=openrouter AI_LLM__API_KEY=..."
        )

    draft = ai.review(bundle, texts, rubric, gate_facts=args.gate_fact or [])

    rule(f"ЧЕРНОВИК · {rubric.title}")
    for verdict in draft.verdicts:
        criterion = rubric.criterion(verdict.criterion_id)
        maximum = f"/{criterion.max_score:g}" if criterion else ""
        flag = " ⚠" if verdict.needs_human_attention else ""
        title = criterion.title if criterion else verdict.criterion_id
        print(f"[{verdict.criterion_id}] {title}: {verdict.score:g}{maximum}{flag}")
        if verdict.verdict:
            print(f"     {verdict.verdict[:100]}")
        for evidence in verdict.evidence:
            print(f"     📎 {evidence.human():<28} [{evidence.status.value}] {evidence.note[:46]}")
        if verdict.attention_reason:
            print(f"     ⚠ {verdict.attention_reason[:100]}")

    print()
    print(explain(aggregate(
        draft.verdicts, rubric,
        submitted_at=bundle.submitted_at, deadline_at=bundle.deadline_at,
    )))
    print(f"\nцитатами подкреплено вердиктов: {draft.evidence_coverage:.0%}")
    if draft.partial_artifacts:
        print(f"показаны не целиком: {', '.join(draft.partial_artifacts)}")
    if draft.failed_criteria:
        print(f"не разобраны: {', '.join(draft.failed_criteria)}")
    print(f"стоимость прогона: {draft.cost_rub} ₽ ({draft.tokens_in} in / {draft.tokens_out} out)")
    return 0


async def cmd_detect(args) -> int:
    bundle = await load_bundle(args)
    config = AIConfig()
    live = config.llm.provider != "fake"
    ai = AIService(config) if live else AIService(
        config, gateway=fake_gateway(['{"findings": []}'])[0]
    )

    texts = await ai.prepare(bundle)
    rule(f"СДАЧА · {bundle.origin_url}")
    describe(texts)

    report = ai.detect(bundle, texts, load_rubric(RUBRIC))

    rule("ДЕТЕКТОР ПРИЗНАКОВ ГенИИ")
    print(
        f"{report.label}: {report.overall_score:.2f} "
        f"[{report.confidence_low:.2f} – {report.confidence_high:.2f}]\n"
    )
    for signal in report.signals:
        mark = {"ok": "  ", "unavailable": "— ", "failed": "! "}[signal.status.value]
        score = f"{signal.score:.2f}" if signal.contributes else "  — "
        print(f"{mark}{signal.kind.value:<11} {score}  вес {signal.weight:.2f}")
        for finding in signal.findings[:2]:
            print(f"       {finding[:86]}")

    if report.spans:
        print("\nспаны:")
        for span in report.spans[:4]:
            print(f"  {span.human():<32} {span.score:.2f}  {span.reason[:60]}")

    print(f"\nдекларация об ИИ: {'найдена' if report.declared_ai_usage else 'не найдена'}")
    if report.mismatch:
        print("расхождение: сигналы есть, декларации нет — это и есть случай для ревьюера")

    print("\nчего проверка не видела:")
    for limit in report.limitations:
        print(f"  - {limit[:100]}")
    print(f"\n{report.advisory_note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Демонстрация ревью-агента и детектора")
    parser.add_argument("--repo", default=None, help="каталог с решением (клон homework_examples)")
    parser.add_argument("--link", default=None, help="ссылка на PR; без неё — записанный бандл")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("review", help="черновик ревью по рубрике")
    p.add_argument("--batch", type=int, default=3)
    p.add_argument("--gate-fact", action="append", help="факт от Format Gate, можно несколько")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("detect", help="сигналы генеративного ИИ")
    p.set_defaults(func=cmd_detect)

    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
