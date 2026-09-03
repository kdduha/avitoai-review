#!/usr/bin/env python3
"""Демонстрация обоих сервисов на реальных работах.

    git clone https://github.com/ai-talent-hub-avito/homework_examples.git

    # детектор: работает без ключа, сигналы в основном детерминированные
    python scripts/demo.py detect --repo homework_examples

    # ревью: без ключа идёт на записанных ответах, с ключом — на живой модели
    AVITOAI_PROVIDER=openrouter AVITOAI_API_KEY=... \\
        python scripts/demo.py review --repo homework_examples
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loader import Bundle, HistoryEvent, load  # noqa: E402

from detection_service import DetectionService, SignalStatus  # noqa: E402
from llm import fake_gateway, gateway_from_env  # noqa: E402
from review_service import ReviewConfig, ReviewService, aggregate, explain  # noqa: E402

GO_SOLUTIONS = [
    ("слабое", "GO/Слабое решение 1-3"),
    ("среднее", "GO/Среднее решение 1-3"),
    ("хорошее", "GO/Хорошее решение 1-3"),
]

RUBRIC_PATH = Path(__file__).resolve().parents[1] / "rubrics" / "go-task1.json"


def rule(title: str) -> None:
    print(f"\n{title}\n" + "─" * 78)


# --------------------------------------------------------------------------- #

def load_rubric():
    """Рубрика через ядро, если оно установлено; иначе — лёгкий разбор JSON."""
    payload = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    try:
        from reviewer_core import Rubric  # type: ignore

        return Rubric.model_validate(payload)
    except ImportError:
        from doubles_rubric import rubric_from_dict

        return rubric_from_dict(payload)


def make_gateway(provider: str, responses: list[str] | None = None):
    if provider == "fake":
        gateway, _ = fake_gateway(responses or [])
        return gateway
    os.environ["AVITOAI_PROVIDER"] = provider
    return gateway_from_env()


def canned_responses(bundle, rubric, batch_size: int) -> list[str]:
    """Правдоподобные ответы модели, собранные из настоящего содержимого работы.

    Нужны, чтобы демо без ключа проходило весь путь целиком, включая сверку
    цитат: цитаты берутся из реальных строк файлов, поэтому валидатор их
    подтверждает так же, как подтвердил бы ответ живой модели. Одна цитата
    намеренно испорчена — чтобы на демо было видно, как отбраковка работает.
    """
    quotes: list[tuple[str, int, str]] = []
    for artifact in bundle.solution_files:
        for number, line in enumerate(artifact.text.splitlines(), start=1):
            stripped = line.strip()
            if len(stripped) > 25 and not stripped.startswith(("//", "#", "import")):
                quotes.append((artifact.path, number, stripped))

    responses: list[str] = []
    criteria = rubric.criteria
    batches = [criteria[i : i + batch_size] for i in range(0, len(criteria), batch_size)]

    index = 0
    spoiled = False
    for batch in batches:
        verdicts = []
        for criterion in batch:
            if quotes:
                path, line, text = quotes[index % len(quotes)]
                index += 7
            else:
                path, line, text = ("README.md", 1, "нет содержимого")

            if not spoiled and len(batch) > 1:
                # Одна выдуманная цитата на прогон: видно, как её отбрасывают.
                text = "здесь реализована ретрай-логика с экспоненциальной задержкой"
                spoiled = True

            verdicts.append({
                "criterion_id": criterion.id,
                "score": round(criterion.max_score * 0.75, 1),
                "confidence": 0.82,
                "verdict": f"Требования критерия «{criterion.title}» выполнены частично.",
                "evidence": [{"artifact": path, "start_line": line,
                              "end_line": line, "quote": text}],
                "student_feedback": "Основа собрана аккуратно, давай докрутим детали.",
                "improvement_hint": "Добавить обработку граничных случаев.",
                "needs_human_attention": False,
                "attention_reason": "",
            })
        responses.append(json.dumps({"verdicts": verdicts}, ensure_ascii=False))
    return responses


# --------------------------------------------------------------------------- #

def cmd_detect(args) -> int:
    repo = Path(args.repo)
    gateway = make_gateway(args.provider) if args.provider != "none" else None
    service = DetectionService(gateway)

    rule("ДЕТЕКТОР ПРИЗНАКОВ ГенИИ · три решения GO")
    for label, rel in GO_SOLUTIONS:
        path = repo / rel
        if not path.exists():
            print(f"{label:<10} нет в репозитории")
            continue

        bundle = load(path, "go-task1")
        report = service.analyse(bundle)

        print(f"\n{label:<10} {report.overall_score:.2f}  "
              f"[{report.confidence_low:.2f} – {report.confidence_high:.2f}]  {report.label}")
        for signal in report.signals:
            mark = {"ok": "  ", "unavailable": "— ", "failed": "! "}[signal.status.value]
            score = f"{signal.score:.2f}" if signal.contributes else "  — "
            print(f"   {mark}{signal.kind.value:<11} {score}  вес {signal.weight:.2f}")
            for finding in signal.findings[:2]:
                print(f"        {finding[:88]}")
        if report.spans:
            print("   спаны:")
            for span in report.spans[:3]:
                print(f"        {span.human()}  {span.score:.2f}  {span.reason[:60]}")
        print(f"   декларация об ИИ: {'найдена' if report.declared_ai_usage else 'не найдена'}")

    rule("ЧТО ЭТОТ ПРОГОН ПОКАЗЫВАЕТ")
    print(
        "Выгрузки организаторов — это снимки без .git, поэтому форензика\n"
        "недоступна и её вес перераспределяется. Это не молчаливое обнуление:\n"
        "ограничение выписано в отчёт, и ревьюер видит, что самый весомый\n"
        "сигнал не смотрел на работу.\n\n"
        "Ниже — тот же детектор на синтетической истории, чтобы показать,\n"
        "что сигнал работает, когда данные есть."
    )

    base = datetime(2026, 2, 8, 2, 0, tzinfo=timezone.utc)
    good = load(repo / GO_SOLUTIONS[2][1], "go-task1")
    good.history = [
        HistoryEvent(at=base, added=14, touched_paths=["go.mod"]),
        HistoryEvent(at=base + timedelta(minutes=3), added=640,
                     touched_paths=["internal/usecase/courier.go"]),
        HistoryEvent(at=base + timedelta(minutes=7), added=25, touched_paths=["README.md"]),
    ]
    report = DetectionService(gateway).analyse(good)
    forensic = report.signal(list(report.signals)[0].kind)
    print(f"\nс историей: {report.overall_score:.2f} "
          f"[{report.confidence_low:.2f} – {report.confidence_high:.2f}] {report.label}")
    for finding in forensic.findings[:2]:
        print(f"   {finding}")
    return 0


def cmd_review(args) -> int:
    repo = Path(args.repo)
    rubric = load_rubric()

    path = repo / (args.solution or GO_SOLUTIONS[2][1])
    if not path.exists():
        print(f"Нет каталога: {path}")
        return 1

    bundle = load(path, rubric.assignment_id)
    bundle.submitted_at = datetime(2026, 2, 8, 20, 0, tzinfo=timezone.utc)
    bundle.deadline_at = datetime(2026, 2, 9, 23, 59, tzinfo=timezone.utc)

    gateway = make_gateway(
        args.provider,
        canned_responses(bundle, rubric, args.batch) if args.provider == "fake" else None,
    )

    rule(f"РЕВЬЮ · {path.name}")
    print(f"файлов: {len(bundle.solution_files)}, "
          f"токенов на входе: ~{sum(a.est_tokens for a in bundle.solution_files)}")

    if args.provider == "fake":
        print("\nПровайдер fake: ответы собраны из настоящих строк работы, модель")
        print("не вызывается. Одна цитата намеренно выдумана — видно отбраковку.")
        print("Живой прогон: AVITOAI_PROVIDER=openrouter AVITOAI_API_KEY=...")

    draft = ReviewService(gateway, ReviewConfig(batch_size=args.batch)).review(
        bundle, rubric,
        gate_facts=args.gate_fact or [],
    )

    print()
    for verdict in draft.verdicts:
        criterion = rubric.criterion(verdict.criterion_id)
        title = criterion.title if criterion else verdict.criterion_id
        flag = " ⚠" if verdict.needs_human_attention else ""
        print(f"[{verdict.criterion_id}] {title}: {verdict.score:g}/{criterion.max_score:g}{flag}")
        if verdict.verdict:
            print(f"     {verdict.verdict[:100]}")
        for evidence in verdict.evidence:
            print(f"     📎 {evidence.human()}  [{evidence.status.value}] {evidence.note[:50]}")
        if verdict.attention_reason:
            print(f"     ⚠ {verdict.attention_reason}")

    print()
    print(explain(aggregate(
        draft.verdicts, rubric,
        submitted_at=bundle.submitted_at, deadline_at=bundle.deadline_at,
    )))
    print(f"\nцитатами подкреплено вердиктов: {draft.evidence_coverage:.0%}")
    print(f"стоимость прогона: {draft.cost_rub} ₽ "
          f"({draft.tokens_in} in / {draft.tokens_out} out)")
    if draft.failed_criteria:
        print(f"не разобраны: {', '.join(draft.failed_criteria)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Демонстрация ревью-агента и детектора")
    parser.add_argument("--repo", default="homework_examples", help="клон homework_examples")
    parser.add_argument("--provider", default=os.getenv("AVITOAI_PROVIDER", "fake"),
                        choices=["fake", "local", "openrouter", "none"])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("detect", help="детектор на трёх решениях GO")
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("review", help="ревью одного решения")
    p.add_argument("--solution", default=None)
    p.add_argument("--batch", type=int, default=3)
    p.add_argument("--gate-fact", action="append", help="факт от Format Gate, можно несколько")
    p.set_defaults(func=cmd_review)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
