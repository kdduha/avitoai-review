"""Кабинет студента: свои задания, сдача по ссылке, свои оценки.

Правило, которое держит весь модуль: **черновик студенту не показывают**.
Пока ревьюер не утвердил разбор, работа для студента «на проверке» и балла у
неё нет. Иначе мы объявили бы студенту оценку, которую поставила модель, — а
ставит её человек, и он ещё не поставил. Ровно по этой же причине сюда не
доезжают ни цитаты, ни уверенность модели, ни отметки «нужен человек»: это
кухня проверки, а не обратная связь.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from avito_reviewer.ai import AIService
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.rubric import Rubric
from avito_reviewer.app.auth import CurrentUser
from avito_reviewer.app.deps import ingest_submission
from avito_reviewer.app.schemas.review import ArtifactTextOut, ReviewRequest
from avito_reviewer.app.schemas.student import (
    StudentAssignment,
    StudentSubmission,
    StudentSubmitRequest,
    StudentVerdict,
)
from avito_reviewer.db import (
    Assignment,
    Course,
    Enrollment,
    Stream,
    Submission,
    SubmissionStatus,
    session_dependency,
)

router = APIRouter(tags=["student"])

Session = Annotated[AsyncSession, Depends(session_dependency)]


# --------------------------------------------------------------------------- #
# вспомогательное
# --------------------------------------------------------------------------- #

async def _my_streams(session: AsyncSession, student_id: UUID) -> list[UUID]:
    return list(
        (
            await session.execute(
                select(Enrollment.stream_id).where(Enrollment.student_id == student_id)
            )
        ).scalars().all()
    )


async def _where(session: AsyncSession, assignment: Assignment) -> tuple[str, str]:
    """Курс и поток задания строками — для подписи в кабинете."""
    stream = await session.get(Stream, assignment.stream_id)
    course = await session.get(Course, stream.course_id) if stream else None
    return (course.key if course else ""), (stream.key if stream else "")


def _rubric_title(rubric: Rubric | None, assignment: Assignment) -> str:
    return assignment.title or (rubric.title if rubric else assignment.rubric_key)


def _student_verdicts(draft: ReviewDraft, rubric: Rubric | None) -> list[StudentVerdict]:
    out = []
    for verdict in draft.verdicts:
        criterion = rubric.criterion(verdict.criterion_id) if rubric else None
        out.append(
            StudentVerdict(
                criterion_id=verdict.criterion_id,
                title=criterion.title if criterion else verdict.criterion_id,
                score=verdict.score,
                max_score=criterion.max_score if criterion else 0.0,
                # `student_feedback` пишется в поддерживающем тоне и предназначен
                # студенту; `verdict` — рабочая формулировка для ревьюера.
                # Пустой feedback лучше заменить рабочей, чем показать пустоту.
                feedback=verdict.student_feedback or verdict.verdict,
                improvement_hint=verdict.improvement_hint,
            )
        )
    return out


async def _as_student_submission(
    session: AsyncSession, request: Request, submission: Submission
) -> StudentSubmission:
    assignment = (
        await session.get(Assignment, submission.assignment_id)
        if submission.assignment_id
        else None
    )
    course_key, stream_key = await _where(session, assignment) if assignment else ("", "")
    rubric = Rubric.model_validate(submission.rubric_snapshot)
    approved = submission.status == SubmissionStatus.APPROVED

    card = StudentSubmission(
        id=submission.id,
        assignment_title=_rubric_title(rubric, assignment) if assignment else rubric.title,
        course_key=course_key,
        stream_key=stream_key,
        origin_url=submission.origin_url,
        submitted_at=submission.submitted_at,
        deadline_at=submission.deadline_at,
        created_at=submission.created_at,
        approved=approved,
        max_score=rubric.scale.total_max,
    )
    if not approved:
        # Здесь и заканчивается всё, что студент видит до утверждения:
        # ссылка, дата и «на проверке». Балл появится, когда его поставит
        # человек, а не когда его посчитала модель.
        return card

    draft = ReviewDraft.model_validate(submission.draft)
    card.score = draft.score
    card.passed = draft.passed
    card.pass_explanation = draft.pass_explanation
    card.late_explanation = draft.late_explanation
    card.verdicts = _student_verdicts(draft, rubric)
    return card


# --------------------------------------------------------------------------- #
# что сдавать
# --------------------------------------------------------------------------- #

@router.get("/me/assignments", summary="Задания моих потоков")
async def my_assignments(
    user: CurrentUser, request: Request, session: Session
) -> list[StudentAssignment]:
    """Только потоки, на которые студент зачислен.

    Не зачислен никуда — пустой список, а не ошибка: это штатное состояние
    аккаунта, который завели, но ещё не добавили в поток.
    """
    streams = await _my_streams(session, user.id)
    if not streams:
        return []

    rows = (
        await session.execute(
            select(Assignment)
            .where(Assignment.stream_id.in_(streams))
            .order_by(Assignment.deadline_at, Assignment.created_at)
        )
    ).scalars().all()

    mine = (
        await session.execute(select(Submission).where(Submission.student_id == user.id))
    ).scalars().all()

    out = []
    for assignment in rows:
        course_key, stream_key = await _where(session, assignment)
        rubric = request.app.state.rubrics.get(assignment.rubric_key)
        attempts = [s for s in mine if s.assignment_id == assignment.id]
        approved = [
            ReviewDraft.model_validate(s.draft).score
            for s in attempts
            if s.status == SubmissionStatus.APPROVED
        ]
        out.append(
            StudentAssignment(
                id=assignment.id,
                course_key=course_key,
                stream_key=stream_key,
                title=_rubric_title(rubric, assignment),
                description=assignment.description,
                max_score=rubric.scale.total_max if rubric else 0.0,
                criteria=len(rubric.criteria) if rubric else 0,
                opens_at=assignment.opens_at,
                deadline_at=assignment.deadline_at,
                submissions=len(attempts),
                best_score=max(approved) if approved else None,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# сдача
# --------------------------------------------------------------------------- #

@router.post("/me/submissions", summary="Сдать работу по ссылке", status_code=201)
async def submit(
    body: StudentSubmitRequest, request: Request, user: CurrentUser, session: Session
) -> StudentSubmission:
    """Сдать работу: ссылка превращается в разбор, разбор ждёт ревьюера.

    Ревьюер сдаче не назначается — она уходит в общий пул, откуда её раздаёт
    руководитель (`POST /submissions/{id}/reassign`). Назначить себе первого
    попавшегося значило бы раздавать работы по порядку прихода, а не по
    нагрузке и темам, — для этого есть `POST /distribute`.

    ``403`` — студент не зачислен на поток этого задания.
    ``404`` — нет такого задания или его рубрики в каталоге.
    ``409`` — задание ещё не открыто.
    """
    assignment = await session.get(Assignment, body.assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")
    if assignment.stream_id not in await _my_streams(session, user.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="вы не зачислены на поток этого задания"
        )

    from datetime import UTC, datetime

    if assignment.opens_at is not None and assignment.opens_at > datetime.now(tz=UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="задание ещё не открыто")

    rubric: Rubric | None = request.app.state.rubrics.get(assignment.rubric_key)
    if rubric is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"рубрики {assignment.rubric_key!r} нет в каталоге",
        )

    # Просрочка не запрещает сдачу: штраф за неё считает агрегатор по
    # `late_policy` рубрики, и решение «поздно, но зачесть» остаётся за
    # правилами курса, а не за этой ручкой.
    ingest_body = ReviewRequest(
        link=body.link,
        source=body.source,
        assignment_id=assignment.id,
        deadline_at=assignment.deadline_at,
    )
    bundle = await ingest_submission(request, ingest_body)

    ai: AIService = request.app.state.ai
    texts = await ai.prepare(bundle)
    draft = await run_in_threadpool(ai.review, bundle, texts, rubric)

    submission = Submission(
        id=bundle.submission_id,
        origin_url=bundle.origin_url,
        source=bundle.source.value,
        rubric_key=rubric.assignment_id,
        rubric_snapshot=rubric.model_dump(mode="json"),
        assignment_id=assignment.id,
        student_id=user.id,
        reviewer_id=None,
        bundle=bundle.model_dump(mode="json"),
        files=[ArtifactTextOut.of(text).model_dump(mode="json") for text in texts],
        draft=draft.model_dump(mode="json"),
        submitted_at=bundle.submitted_at,
        deadline_at=assignment.deadline_at,
    )
    session.add(submission)
    await session.commit()
    return await _as_student_submission(session, request, submission)


# --------------------------------------------------------------------------- #
# свои оценки
# --------------------------------------------------------------------------- #

@router.get("/me/submissions", summary="Мои сданные работы и оценки")
async def my_submissions(
    user: CurrentUser, request: Request, session: Session
) -> list[StudentSubmission]:
    rows = (
        await session.execute(
            select(Submission)
            .where(Submission.student_id == user.id)
            .order_by(Submission.created_at.desc())
        )
    ).scalars().all()
    return [await _as_student_submission(session, request, row) for row in rows]


@router.get("/me/submissions/{submission_id}", summary="Своя работа целиком")
async def my_submission(
    submission_id: UUID, user: CurrentUser, request: Request, session: Session
) -> StudentSubmission:
    """``404`` — чужая работа. Не 403: существование чужой сдачи — тоже сведение."""
    submission = await session.get(Submission, submission_id)
    if submission is None or submission.student_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="работа не найдена")
    return await _as_student_submission(session, request, submission)
