"""Курсы, потоки, задания, зачисление — настройка обучения.

Читать может любой ревьюер: выбирая, против чего проверять работу, он должен
видеть задания своего потока. Менять — методист, потому что дедлайн задним
числом молча пересчитывает штраф за просрочку на всех уже сданных работах
потока, и это не решение того, кто оценивает одну работу.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.ai.rubric import Rubric, RubricStore
from avito_reviewer.app.auth import RequireAdmin, RequireMethodist, RequireReviewer
from avito_reviewer.app.schemas.teaching import (
    AssignmentIn,
    AssignmentOut,
    AssignmentPatch,
    CourseIn,
    CourseOut,
    CoursePatch,
    EnrollIn,
    StreamIn,
    StreamOut,
    StreamPatch,
    StreamStudentRow,
)
from avito_reviewer.db import (
    Assignment,
    Course,
    Enrollment,
    Role,
    Stream,
    StreamReviewer,
    Submission,
    User,
)
from avito_reviewer.db.session import session_dependency

router = APIRouter(tags=["teaching"])

Session = Annotated[AsyncSession, Depends(session_dependency)]


def _rubric_of(request: Request, rubric_key: str) -> Rubric | None:
    store: RubricStore = request.app.state.rubrics
    return store.get(rubric_key)


async def _count(session: AsyncSession, model, column, value) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(model).where(column == value))).scalar_one()
    )


async def _course_or_404(session: AsyncSession, course_id: UUID) -> Course:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="курс не найден")
    return course


async def _stream_or_404(session: AsyncSession, stream_id: UUID) -> Stream:
    stream = await session.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="поток не найден")
    return stream


async def _assignment_out(
    session: AsyncSession, request: Request, assignment: Assignment
) -> AssignmentOut:
    # Явные `get`, а не `assignment.stream` — ленивая связь в async-сессии
    # поднимает MissingGreenlet: подгрузка ушла бы в синхронный контекст.
    stream = await _stream_or_404(session, assignment.stream_id)
    course = await session.get(Course, stream.course_id)
    rubric = _rubric_of(request, assignment.rubric_key)
    return AssignmentOut(
        id=assignment.id,
        stream_id=stream.id,
        stream_key=stream.key,
        course_key=course.key if course else "",
        rubric_key=assignment.rubric_key,
        # Своё название потока важнее: рубрику могли назвать сухо, а поток
        # выдаёт её студентам под своим именем.
        title=assignment.title or (rubric.title if rubric else ""),
        description=assignment.description,
        opens_at=assignment.opens_at,
        deadline_at=assignment.deadline_at,
        rubric_title=rubric.title if rubric else "",
        max_score=rubric.scale.total_max if rubric else 0.0,
        criteria=len(rubric.criteria) if rubric else 0,
        submissions=await _count(
            session, Submission, Submission.assignment_id, assignment.id
        ),
    )


@router.get("/courses", summary="Курсы")
async def list_courses(user: RequireReviewer, session: Session) -> list[CourseOut]:
    courses = (await session.execute(select(Course).order_by(Course.key))).scalars().all()
    return [
        CourseOut(
            id=c.id,
            key=c.key,
            title=c.title,
            streams=await _count(session, Stream, Stream.course_id, c.id),
        )
        for c in courses
    ]


@router.post("/courses", summary="Завести курс", status_code=201)
async def create_course(body: CourseIn, user: RequireMethodist, session: Session) -> CourseOut:
    exists = (
        await session.execute(select(Course).where(Course.key == body.key))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"курс {body.key!r} уже есть")
    course = Course(key=body.key, title=body.title)
    session.add(course)
    await session.commit()
    return CourseOut(id=course.id, key=course.key, title=course.title, streams=0)


@router.patch("/courses/{course_id}", summary="Переименовать курс")
async def patch_course(
    course_id: UUID, body: CoursePatch, user: RequireMethodist, session: Session
) -> CourseOut:
    course = await _course_or_404(session, course_id)
    course.title = body.title
    await session.commit()
    return CourseOut(
        id=course.id,
        key=course.key,
        title=course.title,
        streams=await _count(session, Stream, Stream.course_id, course.id),
    )


@router.delete("/courses/{course_id}", summary="Убрать курс", status_code=204)
async def delete_course(course_id: UUID, user: RequireAdmin, session: Session) -> None:
    """``409`` — у курса есть потоки: удалить их вместе с ним значило бы снести
    задания и зачисления, о которых спрашивали не здесь."""
    course = await _course_or_404(session, course_id)
    streams = await _count(session, Stream, Stream.course_id, course.id)
    if streams:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"у курса есть потоки ({streams}), удалить нельзя"
        )
    await session.delete(course)
    await session.commit()


@router.get("/streams", summary="Потоки")
async def list_streams(
    user: RequireReviewer, session: Session, course_id: UUID | None = None
) -> list[StreamOut]:
    query = select(Stream).order_by(Stream.key)
    if course_id is not None:
        query = query.where(Stream.course_id == course_id)
    streams = (await session.execute(query)).scalars().all()
    out = []
    for s in streams:
        course = await session.get(Course, s.course_id)
        out.append(
            StreamOut(
                id=s.id,
                course_id=s.course_id,
                course_key=course.key if course else "",
                key=s.key,
                title=s.title,
                assignments=await _count(session, Assignment, Assignment.stream_id, s.id),
                students=await _count(session, Enrollment, Enrollment.stream_id, s.id),
            )
        )
    return out


@router.post("/streams", summary="Завести поток", status_code=201)
async def create_stream(body: StreamIn, user: RequireMethodist, session: Session) -> StreamOut:
    course = await session.get(Course, body.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="курс не найден")
    exists = (
        await session.execute(
            select(Stream).where(Stream.course_id == course.id, Stream.key == body.key)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"поток {body.key!r} у этого курса уже есть"
        )
    stream = Stream(course_id=course.id, key=body.key, title=body.title)
    session.add(stream)
    await session.commit()
    return StreamOut(
        id=stream.id,
        course_id=course.id,
        course_key=course.key,
        key=stream.key,
        title=stream.title,
    )


@router.post("/streams/{stream_id}/students", summary="Зачислить студентов на поток")
async def enroll(
    stream_id: UUID, body: EnrollIn, user: RequireMethodist, session: Session
) -> dict[str, int]:
    """Связать уже заведённые аккаунты с потоком.

    Людей эта ручка не создаёт: аккаунт заводится через `POST /users`, и
    зачислять можно только роль `student` — ревьюер на потоке появляется
    назначением, а не зачислением.
    """
    stream = await _stream_or_404(session, stream_id)
    users = (
        await session.execute(select(User).where(User.username.in_(body.usernames)))
    ).scalars().all()
    found = {u.username: u for u in users}
    missing = [name for name in body.usernames if name not in found]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"нет таких аккаунтов: {', '.join(missing)}"
        )
    not_students = [u.username for u in users if u.role != Role.STUDENT]
    if not_students:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"не студенты: {', '.join(not_students)}",
        )

    already = set(
        (
            await session.execute(
                select(Enrollment.student_id).where(Enrollment.stream_id == stream.id)
            )
        ).scalars().all()
    )
    added = 0
    for u in users:
        if u.id in already:
            continue
        session.add(Enrollment(stream_id=stream.id, student_id=u.id))
        added += 1
    await session.commit()
    return {"enrolled": added, "already": len(users) - added}


@router.patch("/streams/{stream_id}", summary="Переименовать поток")
async def patch_stream(
    stream_id: UUID, body: StreamPatch, user: RequireMethodist, session: Session
) -> StreamOut:
    """``409`` — такой ключ у этого курса уже занят."""
    stream = await _stream_or_404(session, stream_id)
    if body.key is not None and body.key != stream.key:
        taken = (
            await session.execute(
                select(Stream).where(Stream.course_id == stream.course_id, Stream.key == body.key)
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"поток {body.key!r} у этого курса уже есть"
            )
        stream.key = body.key
    if body.title is not None:
        stream.title = body.title
    await session.commit()
    course = await session.get(Course, stream.course_id)
    return StreamOut(
        id=stream.id,
        course_id=stream.course_id,
        course_key=course.key if course else "",
        key=stream.key,
        title=stream.title,
        assignments=await _count(session, Assignment, Assignment.stream_id, stream.id),
        students=await _count(session, Enrollment, Enrollment.stream_id, stream.id),
    )


@router.delete("/streams/{stream_id}", summary="Убрать поток", status_code=204)
async def delete_stream(stream_id: UUID, user: RequireAdmin, session: Session) -> None:
    """``409`` — на потоке есть задания или студенты.

    Назначения ревьюеров уходят вместе с потоком: это список «кому можно
    давать работы этого потока», и без потока он не значит ничего.
    """
    stream = await _stream_or_404(session, stream_id)
    assignments = await _count(session, Assignment, Assignment.stream_id, stream.id)
    students = await _count(session, Enrollment, Enrollment.stream_id, stream.id)
    if assignments or students:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"на потоке задания ({assignments}) и студенты ({students}), удалить нельзя",
        )
    links = (
        await session.execute(select(StreamReviewer).where(StreamReviewer.stream_id == stream.id))
    ).scalars().all()
    for link in links:
        await session.delete(link)
    await session.delete(stream)
    await session.commit()


@router.get("/streams/{stream_id}/students", summary="Состав потока")
async def stream_students(
    stream_id: UUID, user: RequireReviewer, session: Session
) -> list[StreamStudentRow]:
    await _stream_or_404(session, stream_id)
    rows = (
        await session.execute(
            select(User)
            .join(Enrollment, Enrollment.student_id == User.id)
            .where(Enrollment.stream_id == stream_id)
            .order_by(User.username)
        )
    ).scalars().all()
    return [
        StreamStudentRow(
            id=row.id, username=row.username, display_name=row.display_name or row.username
        )
        for row in rows
    ]


@router.delete(
    "/streams/{stream_id}/students/{username}", summary="Отчислить студента", status_code=204
)
async def unenroll(
    stream_id: UUID, username: str, user: RequireMethodist, session: Session
) -> None:
    """Уже сданные работы остаются: отчисление закрывает доступ к заданиям
    потока, а не стирает то, что человек сдал."""
    await _stream_or_404(session, stream_id)
    account = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="аккаунт не найден")
    link = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.stream_id == stream_id, Enrollment.student_id == account.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="студент не на этом потоке")
    await session.delete(link)
    await session.commit()


@router.get("/assignments", summary="Задания")
async def list_assignments(
    request: Request, user: RequireReviewer, session: Session, stream_id: UUID | None = None
) -> list[AssignmentOut]:
    query = select(Assignment).order_by(Assignment.created_at)
    if stream_id is not None:
        query = query.where(Assignment.stream_id == stream_id)
    rows = (await session.execute(query)).scalars().all()
    return [await _assignment_out(session, request, a) for a in rows]


@router.get("/assignments/{assignment_id}", summary="Одно задание")
async def get_assignment(
    assignment_id: UUID, request: Request, user: RequireReviewer, session: Session
) -> AssignmentOut:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")
    return await _assignment_out(session, request, assignment)


@router.post("/assignments", summary="Выдать рубрику потоку", status_code=201)
async def create_assignment(
    body: AssignmentIn, request: Request, user: RequireMethodist, session: Session
) -> AssignmentOut:
    """Завести задание: какая рубрика, какому потоку, до какого числа.

    ``404`` — нет такого потока или такой рубрики в каталоге.
    ``409`` — эта рубрика уже выдана этому потоку.
    """
    stream = await _stream_or_404(session, body.stream_id)
    if _rubric_of(request, body.rubric_key) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"рубрики {body.rubric_key!r} нет в каталоге"
        )
    exists = (
        await session.execute(
            select(Assignment).where(
                Assignment.stream_id == stream.id, Assignment.rubric_key == body.rubric_key
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"рубрика {body.rubric_key!r} уже выдана этому потоку",
        )

    assignment = Assignment(
        stream_id=stream.id,
        rubric_key=body.rubric_key,
        title=body.title,
        description=body.description,
        opens_at=body.opens_at,
        deadline_at=body.deadline_at,
    )
    session.add(assignment)
    await session.commit()
    return await _assignment_out(session, request, assignment)


@router.patch("/assignments/{assignment_id}", summary="Поправить задание или срок")
async def patch_assignment(
    assignment_id: UUID,
    body: AssignmentPatch,
    request: Request,
    user: RequireMethodist,
    session: Session,
) -> AssignmentOut:
    """Правка срока действует только на будущие разборы.

    Уже сохранённые сдачи хранят `deadline_at` в своей строке и в бандле, и
    пересчёт по ним не запускается: работа была оценена против того срока,
    который стоял в момент сдачи, и менять её балл задним числом нельзя —
    ровно по той же причине, по которой рубрика замораживается снимком.
    """
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")

    if body.title is not None:
        assignment.title = body.title
    if body.description is not None:
        assignment.description = body.description
    if body.opens_at is not None:
        assignment.opens_at = body.opens_at
    if body.clear_deadline:
        assignment.deadline_at = None
    elif body.deadline_at is not None:
        assignment.deadline_at = body.deadline_at

    await session.commit()
    return await _assignment_out(session, request, assignment)


@router.delete("/assignments/{assignment_id}", summary="Убрать задание", status_code=204)
async def delete_assignment(
    assignment_id: UUID, user: RequireMethodist, session: Session
) -> None:
    """``409`` — по заданию уже есть сдачи: они ссылаются на него, и удаление
    оставило бы их без объяснения, откуда взялся срок."""
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")
    used = await _count(session, Submission, Submission.assignment_id, assignment.id)
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"по заданию есть сдачи ({used}), удалить нельзя",
        )
    await session.delete(assignment)
    await session.commit()
