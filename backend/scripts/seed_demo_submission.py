"""Одна показательная сдача студента: зачёт, утверждённый ревьюером.

Зачем скрипт, а не запись в таблицу руками: черновик тут получается настоящим.
Он проходит тот же гейт, тот же агрегатор и ту же сверку цитат, что живой
прогон, — записаны только ответы модели, и цитаты в них взяты из настоящих
строк настоящего файла. Черновик, вписанный в базу как есть, разошёлся бы с
кодом при первой же правке рубрики и врал бы на демонстрации убедительнее,
чем отсутствие примера.

    uv run python scripts/seed_demo_submission.py

Идемпотентно: сдача студента с этим origin_url заводится один раз.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from avito_reviewer.ai import AIService
from avito_reviewer.ai.content import ArtifactText, solution_texts
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.ai.rubric import Rubric, RubricStore
from avito_reviewer.app.schemas.review import ArtifactTextOut
from avito_reviewer.config import AppConfig
from avito_reviewer.db import (
    Assignment,
    Course,
    Enrollment,
    Stream,
    Submission,
    SubmissionStatus,
    User,
    make_engine,
    make_sessionmaker,
)
from avito_reviewer.ingest import SubmissionBundle

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts" / "fixtures" / "go-task1-pr42.json"
RUBRIC_KEY = "go-task1"


def full_marks(texts: list[ArtifactText], rubric: Rubric, batch_size: int) -> list[str]:
    """Ответы модели на «всё выполнено» — с цитатами из настоящих строк.

    Цитаты не сочиняются: берутся содержательные строки сданных файлов, и
    валидатор сверяет их с текстом ровно так же, как на живом прогоне. Если бы
    они были выдуманы, вердикты приехали бы с пометкой «нужен человек», и
    пример успешной сдачи перестал бы быть примером успешной сдачи.
    """
    quotes = [
        (text.path, number, line.strip())
        for text in texts
        for number, line in zip(text.line_numbers, text.lines, strict=False)
        if len(line.strip()) > 25 and not line.strip().startswith(("//", "#", "import"))
    ]
    criteria = rubric.criteria
    batches = [criteria[i : i + batch_size] for i in range(0, len(criteria), batch_size)]

    out: list[str] = []
    index = 0
    for batch in batches:
        verdicts = []
        for criterion in batch:
            path, line, quote = (
                quotes[index % len(quotes)] if quotes else ("README.md", 1, "нет содержимого")
            )
            index += 5
            verdicts.append(
                {
                    "criterion_id": criterion.id,
                    "score": criterion.max_score,
                    "confidence": 0.9,
                    "verdict": f"Требования критерия «{criterion.title}» выполнены.",
                    "evidence": [
                        {"artifact": path, "start_line": line, "end_line": line, "quote": quote}
                    ],
                    "student_feedback": (
                        "Сделано аккуратно: структура читается, поведение соответствует условию."
                    ),
                    "improvement_hint": "",
                    "needs_human_attention": False,
                    "attention_reason": "",
                }
            )
        out.append(json.dumps({"verdicts": verdicts}, ensure_ascii=False))

    # Последним идёт итоговый отзыв: он пересказывает уже проставленные
    # вердикты, поэтому и записан здесь, а не выдуман отдельно от них.
    out.append(
        json.dumps(
            {
                "strengths": [
                    "Раскладка соответствует golang-standards: точка входа в cmd, "
                    "внутренние пакеты в internal.",
                    "Веб-сервер поднимается и корректно завершается по сигналу.",
                    "Эндпоинты /ping и /healthcheck на месте и отвечают.",
                ],
                "improvements": [],
                "encouragement": (
                    "Работа собрана аккуратно и по условию — так и держи "
                    "на следующем этапе."
                ),
            },
            ensure_ascii=False,
        )
    )
    return out


async def main() -> int:
    config = AppConfig()
    bundle = SubmissionBundle.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    rubrics = RubricStore(config.ai.rubrics_dir)
    rubric = rubrics.get(RUBRIC_KEY)
    if rubric is None:
        print(f"нет рубрики {RUBRIC_KEY!r} в каталоге")
        return 1

    engine = make_engine(config.db)
    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as session:
        student = (
            await session.execute(select(User).where(User.username == "student"))
        ).scalar_one_or_none()
        if student is None:
            print("нет аккаунта student — сначала поднимите сервис, он сеет аккаунты")
            return 1

        already = (
            await session.execute(
                select(Submission).where(
                    Submission.student_id == student.id,
                    Submission.origin_url == bundle.origin_url,
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            print(f"показательная сдача уже есть: {already.id}")
            return 0

        # Курс, поток и задание — те же, что заводит методист руками.
        course = (
            await session.execute(select(Course).where(Course.key == "go"))
        ).scalar_one_or_none()
        if course is None:
            course = Course(key="go", title="Разработка на Go")
            session.add(course)
            await session.flush()
        stream = (
            await session.execute(
                select(Stream).where(Stream.course_id == course.id, Stream.key == "a")
            )
        ).scalar_one_or_none()
        if stream is None:
            stream = Stream(course_id=course.id, key="a", title="Поток 2, осень 2026")
            session.add(stream)
            await session.flush()
        assignment = (
            await session.execute(
                select(Assignment).where(
                    Assignment.stream_id == stream.id, Assignment.rubric_key == RUBRIC_KEY
                )
            )
        ).scalar_one_or_none()
        if assignment is None:
            assignment = Assignment(
                stream_id=stream.id,
                rubric_key=RUBRIC_KEY,
                description="Сдаём pull request в свой форк. Тесты обязательны.",
            )
            session.add(assignment)
            await session.flush()
        enrolled = (
            await session.execute(
                select(Enrollment).where(
                    Enrollment.stream_id == stream.id, Enrollment.student_id == student.id
                )
            )
        ).scalar_one_or_none()
        if enrolled is None:
            session.add(Enrollment(stream_id=stream.id, student_id=student.id))

        # Сеяный `reviewer`, а не карточка каталога: под этим логином входит
        # переключатель ролей, и показательная сдача должна открываться там,
        # где её будут смотреть. Назначенная на `c-kruglov`, она была видна
        # только руководителю — остальным `_load` отдаёт 404, потому что
        # чужая сдача не должна существовать даже как факт.
        reviewer = (
            await session.execute(select(User).where(User.username == "reviewer"))
        ).scalar_one_or_none() or (
            await session.execute(select(User).where(User.username == "c-kruglov"))
        ).scalar_one_or_none()

        # Настоящий конвейер на записанных ответах: гейт, сверка цитат, агрегатор.
        probe = AIService(config.ai, gateway=fake_gateway([])[0])
        texts = await probe.prepare(bundle)
        ai = AIService(
            config.ai,
            gateway=fake_gateway(
                full_marks(solution_texts(texts), rubric, config.ai.review.batch_size)
            )[0],
        )
        draft = ai.review(bundle, texts, rubric)

        submission = Submission(
            id=bundle.submission_id,
            origin_url=bundle.origin_url,
            source=bundle.source.value,
            rubric_key=rubric.assignment_id,
            rubric_snapshot=rubric.model_dump(mode="json"),
            assignment_id=assignment.id,
            student_id=student.id,
            reviewer_id=reviewer.id if reviewer else None,
            approved_by=reviewer.id if reviewer else None,
            status=SubmissionStatus.APPROVED,
            bundle=bundle.model_dump(mode="json"),
            files=[ArtifactTextOut.of(text).model_dump(mode="json") for text in texts],
            draft=draft.model_dump(mode="json"),
            submitted_at=bundle.submitted_at,
            deadline_at=assignment.deadline_at,
        )
        from datetime import UTC, datetime

        submission.approved_at = datetime.now(tz=UTC)
        session.add(submission)
        await session.commit()

    await engine.dispose()
    print(
        f"сдача {submission.id}: {draft.score:g} из {draft.max_score:g}, "
        f"{'зачёт' if draft.passed else 'не зачтено'}, "
        f"цитат подтверждено {draft.evidence_coverage:.0%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
