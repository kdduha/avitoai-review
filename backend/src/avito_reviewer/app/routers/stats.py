"""Статистика потоков и заданий + ревьюеры на потоке и раскладка работ по ним.

Числа считаются по строкам `submissions`, а не по генератору: до сих пор
дашборды курса жили на синтетике и не знали ни о сдачах, ни о заданиях.
Отсюда правило: **чего не записано, того не показываем**. Утверждённых работ
нет — среднего балла нет, и на его месте `None`, а не ноль: ноль читается как
«все написали на ноль».
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.app.auth import RequireAdmin, RequireReviewer
from avito_reviewer.app.schemas.stats import (
    AssignmentStats,
    AssignReviewersRequest,
    DistributeResult,
    ReviewerLoadRow,
    ScoreBucket,
    StreamReviewerRow,
    StreamStats,
)
from avito_reviewer.db import (
    Assignment,
    Course,
    Enrollment,
    Role,
    Stream,
    StreamReviewer,
    Submission,
    SubmissionStatus,
    User,
    session_dependency,
)
from avito_reviewer.distribution import DistributionItem, Reviewer, distribute

router = APIRouter(tags=["stats"])

Session = Annotated[AsyncSession, Depends(session_dependency)]

_BUCKETS = ((0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))
"""Четыре корзины по доле максимума. В баллах их строить нельзя: у заданий
шкалы 6, 10 и 20, и одна гистограмма на поток иначе несравнима сама с собой."""

def _estimate_minutes(criteria: int) -> int:
    """Во сколько обойдётся разбор — грубо, зато без обращения к модели.

    Солвер отказывается принимать работу без оценки трудоёмкости, и это
    правильно: раскладывать в минутах, не зная минут, — самообман. Настоящую
    оценку даёт `POST /work-profile`, но она стоит вызова модели на каждую
    работу, а раскладка запускается на весь поток разом. Пока профилей нет,
    берём число критериев: оно хотя бы отличает разбор из пяти пунктов от
    разбора из двадцати, и одинаково для всех ревьюеров — то есть не искажает
    сравнение между ними.
    """
    return max(20, criteria * 6)


_DEFAULT_CAPACITY_MINUTES = 300
"""Ёмкость ревьюера без карточки в каталоге. Подписана в ответе, а не
подставлена молча: заявленное должно быть отличимо от измеренного."""


async def _stream_or_404(session: AsyncSession, stream_id: UUID) -> Stream:
    stream = await session.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="поток не найден")
    return stream


async def _count(session: AsyncSession, model, column, value) -> int:
    rows = (await session.execute(select(model).where(column == value))).scalars().all()
    return len(rows)


def _approved(submissions: list[Submission]) -> list[Submission]:
    return [s for s in submissions if s.status == SubmissionStatus.APPROVED]


def _drafts(submissions: list[Submission]) -> list[ReviewDraft]:
    return [ReviewDraft.model_validate(s.draft) for s in submissions]


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _histogram(drafts: list[ReviewDraft]) -> list[ScoreBucket]:
    buckets = [ScoreBucket(lo=lo, hi=hi, count=0) for lo, hi in _BUCKETS]
    for draft in drafts:
        if draft.max_score <= 0:
            continue
        share = draft.score / draft.max_score
        for bucket in buckets:
            # Верхняя граница включается только у последней корзины, иначе
            # работа на максимум не попадает никуда.
            if bucket.lo <= share < bucket.hi or (bucket.hi == 1.0 and share >= bucket.hi):
                bucket.count += 1
                break
    return buckets


def _aware(value: datetime | None) -> datetime | None:
    """Дата из базы — всегда с зоной.

    Колонки объявлены `DateTime(timezone=True)`, но SQLite зону не хранит и
    возвращает наивное время; Postgres — осведомлённое. Сравнение наивного с
    осведомлённым падает TypeError, и падает только на тестах либо только в
    проде — смотря где повезёт. Тот же капкан уже ловили в распределении.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_late(submission: Submission) -> bool:
    deadline, submitted = _aware(submission.deadline_at), _aware(submission.submitted_at)
    return bool(deadline and submitted and submitted > deadline)


async def _assignment_stats(
    session: AsyncSession,
    request: Request,
    assignment: Assignment,
    submissions: list[Submission],
    *,
    course_key: str,
    stream_key: str,
) -> AssignmentStats:
    rubric = request.app.state.rubrics.get(assignment.rubric_key)
    mine = [s for s in submissions if s.assignment_id == assignment.id]
    approved = _approved(mine)
    drafts = _drafts(approved)

    return AssignmentStats(
        id=assignment.id,
        rubric_key=assignment.rubric_key,
        title=assignment.title or (rubric.title if rubric else assignment.rubric_key),
        course_key=course_key,
        stream_key=stream_key,
        deadline_at=assignment.deadline_at,
        max_score=rubric.scale.total_max if rubric else 0.0,
        submissions=len(mine),
        awaiting=len(mine) - len(approved),
        approved=len(approved),
        late=sum(1 for s in mine if _is_late(s)),
        average_score=_average([d.score for d in drafts]),
        pass_rate=(
            round(sum(1 for d in drafts if d.passed) / len(drafts), 2) if drafts else None
        ),
        needs_attention=sum(1 for d in _drafts(mine) if d.needs_human_attention),
        histogram=_histogram(drafts),
    )


@router.get("/stats/streams/{stream_id}", summary="Статистика потока")
async def stream_stats(
    stream_id: UUID, request: Request, user: RequireReviewer, session: Session
) -> StreamStats:
    """Что происходит на потоке: сдачи, очередь, просрочка, баллы.

    Доступно ревьюеру: он должен видеть, как идёт поток, который проверяет, —
    и это же требуется методисту и руководителю. Ограничивать чтение статистики
    ролью выше значило бы прятать от человека результат его же работы.
    """
    stream = await _stream_or_404(session, stream_id)
    course = await session.get(Course, stream.course_id)
    course_key = course.key if course else ""

    assignments = (
        await session.execute(
            select(Assignment).where(Assignment.stream_id == stream.id).order_by(Assignment.created_at)
        )
    ).scalars().all()
    ids = [a.id for a in assignments]
    submissions = (
        (
            await session.execute(select(Submission).where(Submission.assignment_id.in_(ids)))
        ).scalars().all()
        if ids
        else []
    )
    submissions = list(submissions)
    approved = _approved(submissions)
    drafts = _drafts(approved)
    now = datetime.now(tz=UTC)

    reviewer_rows: list[ReviewerLoadRow] = []
    links = (
        await session.execute(select(StreamReviewer).where(StreamReviewer.stream_id == stream.id))
    ).scalars().all()
    for link in links:
        account = await session.get(User, link.reviewer_id)
        if account is None:
            continue
        theirs = [s for s in submissions if s.reviewer_id == account.id]
        reviewer_rows.append(
            ReviewerLoadRow(
                username=account.username,
                display_name=account.display_name or account.username,
                assigned=len(theirs),
                approved=len(_approved(theirs)),
                awaiting=len(theirs) - len(_approved(theirs)),
            )
        )

    return StreamStats(
        id=stream.id,
        course_key=course_key,
        stream_key=stream.key,
        title=stream.title,
        students=await _count(session, Enrollment, Enrollment.stream_id, stream.id),
        reviewers=len(links),
        assignments=len(assignments),
        submissions=len(submissions),
        awaiting=len(submissions) - len(approved),
        approved=len(approved),
        unassigned=sum(1 for s in submissions if s.reviewer_id is None),
        overdue=sum(
            1
            for s in submissions
            if (deadline := _aware(s.deadline_at))
            and deadline < now
            and s.status != SubmissionStatus.APPROVED
        ),
        average_score=_average([d.score for d in drafts]),
        pass_rate=(
            round(sum(1 for d in drafts if d.passed) / len(drafts), 2) if drafts else None
        ),
        by_assignment=[
            await _assignment_stats(
                session, request, a, submissions, course_key=course_key, stream_key=stream.key
            )
            for a in assignments
        ],
        by_reviewer=sorted(reviewer_rows, key=lambda r: r.username),
    )


@router.get("/stats/assignments/{assignment_id}", summary="Статистика задания")
async def assignment_stats(
    assignment_id: UUID, request: Request, user: RequireReviewer, session: Session
) -> AssignmentStats:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")
    stream = await _stream_or_404(session, assignment.stream_id)
    course = await session.get(Course, stream.course_id)
    submissions = list(
        (
            await session.execute(
                select(Submission).where(Submission.assignment_id == assignment.id)
            )
        ).scalars().all()
    )
    return await _assignment_stats(
        session,
        request,
        assignment,
        submissions,
        course_key=course.key if course else "",
        stream_key=stream.key,
    )


def _roster_card(request: Request, account: User) -> Reviewer | None:
    """Карточка каталога, если она есть.

    Каталог ведут файлами, аккаунты живут в базе, общего ключа между ними нет —
    связываем по логину или почте. Не нашлось — не ошибка: распределение возьмёт
    ёмкость по умолчанию, и в ответе это будет видно (`roster_id: null`).
    """
    store = request.app.state.reviewers
    for card in store.all():
        if card.id == account.username or (card.email and card.email == account.username):
            return card
    return None


@router.get("/streams/{stream_id}/reviewers", summary="Ревьюеры потока")
async def stream_reviewers(
    stream_id: UUID, request: Request, user: RequireReviewer, session: Session
) -> list[StreamReviewerRow]:
    await _stream_or_404(session, stream_id)
    links = (
        await session.execute(select(StreamReviewer).where(StreamReviewer.stream_id == stream_id))
    ).scalars().all()

    rows = []
    for link in links:
        account = await session.get(User, link.reviewer_id)
        if account is None:
            continue
        card = _roster_card(request, account)
        rows.append(
            StreamReviewerRow(
                username=account.username,
                display_name=account.display_name or account.username,
                role=str(account.role),
                roster_id=card.id if card else None,
                capacity_minutes=card.capacity_minutes if card else _DEFAULT_CAPACITY_MINUTES,
                skills=card.skills if card else [],
            )
        )
    return sorted(rows, key=lambda r: r.username)


@router.post("/streams/{stream_id}/reviewers", summary="Назначить ревьюеров на поток")
async def assign_reviewers(
    stream_id: UUID,
    body: AssignReviewersRequest,
    request: Request,
    user: RequireAdmin,
    session: Session,
) -> list[StreamReviewerRow]:
    """``422`` — среди названных есть студент: проверять работы он не может."""
    await _stream_or_404(session, stream_id)
    accounts = (
        await session.execute(select(User).where(User.username.in_(body.usernames)))
    ).scalars().all()
    found = {a.username for a in accounts}
    missing = [name for name in body.usernames if name not in found]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"нет таких аккаунтов: {', '.join(missing)}"
        )
    students = [a.username for a in accounts if a.role == Role.STUDENT]
    if students:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"работы не проверяют: {', '.join(students)}",
        )

    already = {
        link.reviewer_id
        for link in (
            await session.execute(
                select(StreamReviewer).where(StreamReviewer.stream_id == stream_id)
            )
        ).scalars().all()
    }
    for account in accounts:
        if account.id not in already:
            session.add(StreamReviewer(stream_id=stream_id, reviewer_id=account.id))
    await session.commit()
    return await stream_reviewers(stream_id, request, user, session)


@router.delete(
    "/streams/{stream_id}/reviewers/{username}",
    summary="Снять ревьюера с потока",
    status_code=204,
)
async def unassign_reviewer(
    stream_id: UUID, username: str, user: RequireAdmin, session: Session
) -> None:
    """Уже выданные этому ревьюеру работы остаются за ним.

    Снятие с потока значит «больше не давать новых», а не «отобрать начатое»:
    переброс конкретной работы — это `POST /submissions/{id}/reassign`, и он
    должен оставаться видимым действием, а не побочным эффектом.
    """
    account = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="аккаунт не найден")
    link = (
        await session.execute(
            select(StreamReviewer).where(
                StreamReviewer.stream_id == stream_id,
                StreamReviewer.reviewer_id == account.id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ревьюер не на этом потоке")
    await session.delete(link)
    await session.commit()


@router.post("/streams/{stream_id}/distribute", summary="Разложить нераспределённые работы")
async def distribute_stream(
    stream_id: UUID, request: Request, user: RequireAdmin, session: Session
) -> DistributeResult:
    """Раздать работы потока его ревьюерам — и записать результат в базу.

    Раньше `POST /distribute` считал план по пулу из тела запроса и возвращал
    его наружу; план никуда не сохранялся, и назначение оставалось на совести
    того, кто его прочитал. Здесь тот же солвер, но вход берётся из базы, а
    выход в неё же и ложится: у сдачи появляется `reviewer_id`.

    Трогаются только работы **без ревьюера**. Уже назначенные не
    перекладываются: ревьюер мог начать разбор, и молча отобрать у него работу
    хуже, чем оставить перекос в нагрузке.

    ``409`` — на потоке нет ни одного ревьюера.
    """
    await _stream_or_404(session, stream_id)

    links = (
        await session.execute(select(StreamReviewer).where(StreamReviewer.stream_id == stream_id))
    ).scalars().all()
    accounts = [a for a in [await session.get(User, link.reviewer_id) for link in links] if a]
    if not accounts:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="на потоке нет ревьюеров — некому раздавать"
        )

    assignments = (
        await session.execute(select(Assignment).where(Assignment.stream_id == stream_id))
    ).scalars().all()
    by_id = {a.id: a for a in assignments}
    if not by_id:
        return DistributeResult(assigned=0, unassigned=0)

    submissions = list(
        (
            await session.execute(
                select(Submission).where(
                    Submission.assignment_id.in_(list(by_id)),
                    Submission.reviewer_id.is_(None),
                )
            )
        ).scalars().all()
    )
    if not submissions:
        return DistributeResult(assigned=0, unassigned=0)

    # Домен не знает про наши таблицы: карточка ревьюера собирается из аккаунта,
    # а из каталога подмешивается только то, что там есть.
    reviewers = []
    for account in accounts:
        card = _roster_card(request, account)
        reviewers.append(
            Reviewer(
                id=str(account.id),
                name=account.display_name or account.username,
                skills=card.skills if card else [],
                capacity_minutes=card.capacity_minutes if card else _DEFAULT_CAPACITY_MINUTES,
                median_minutes_per_work=card.median_minutes_per_work if card else 0.0,
                onboarding=card.onboarding if card else False,
            )
        )

    def minutes_for(submission: Submission) -> int:
        assignment = by_id.get(submission.assignment_id) if submission.assignment_id else None
        rubric = request.app.state.rubrics.get(assignment.rubric_key) if assignment else None
        return _estimate_minutes(len(rubric.criteria) if rubric else 0)

    items = [
        DistributionItem(
            item_id=str(s.id),
            assignment_id=by_id[s.assignment_id].rubric_key if s.assignment_id else "",
            stream_id=str(stream_id),
            due_at=_aware(s.deadline_at),
            est_review_minutes=minutes_for(s),
        )
        for s in submissions
    ]

    # Уже занятые минуты — из назначенных, но не утверждённых работ: солвер
    # обязан видеть текущую нагрузку, иначе разложит поверх неё.
    busy = list(
        (
            await session.execute(
                select(Submission).where(
                    Submission.assignment_id.in_(list(by_id)),
                    Submission.reviewer_id.is_not(None),
                    Submission.status != SubmissionStatus.APPROVED,
                )
            )
        ).scalars().all()
    )
    committed: dict[str, int] = {}
    for s in busy:
        key = str(s.reviewer_id)
        committed[key] = committed.get(key, 0) + minutes_for(s)

    plan = distribute(items, reviewers, committed_minutes=committed)

    by_submission = {str(s.id): s for s in submissions}
    for allocation in plan.allocations:
        submission = by_submission.get(allocation.item_id)
        if submission is not None:
            submission.reviewer_id = UUID(allocation.reviewer_id)
    await session.commit()

    return DistributeResult(
        assigned=len(plan.allocations),
        unassigned=len(plan.unassigned),
        reasons=[f"{u.reason.value}: {u.detail}" for u in plan.unassigned],
    )
