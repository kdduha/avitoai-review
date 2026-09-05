"""Persisted state: users, submissions, review revisions, chat messages.

Four tables, not the whole schema in `docs/architecture.md` §10 — that
diagram is the target shape for a system with an Assignment Engine, courses
and a rubric editor. What backs today's endpoints is smaller: a submission
*is* a `SubmissionBundle` + `ReviewDraft` + `DetectionReport` the pipeline
already produces, stored as JSON next to who owns it and what happened to it.
Splitting artifacts, revisions or spans into their own tables would just be
ORM ceremony around data these Pydantic models already shape correctly.
`ChatMessage` is the one thing that genuinely needs its own rows: a
conversation is a sequence, and reviewers reopening a submission expect their
chat history still there — an in-memory-only chat is a stub with a UI on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

_TZ_DATETIME = DateTime(timezone=True)
"""Every datetime this app produces is UTC-aware (ingest, JWT, `datetime.now(tz=UTC)`).

Postgres's plain `TIMESTAMP` is timezone-*naive* and asyncpg refuses an aware
value against it outright; SQLite does not care either way. Without this,
persisting a submission works in tests (SQLite) and 500s in docker-compose
(Postgres) the first time a real PR's `submitted_at` reaches the database."""


class Base(DeclarativeBase):
    pass


class Role(StrEnum):
    """RBAC roles: four, matching the words the organisers actually use.

    `methodist` owns what a work is judged against — rubrics, assignment
    descriptions, deadlines. `reviewer` judges works against it. Splitting
    them is not bureaucracy: a deadline change silently rescores every late
    submission on the stream, and that is not a call the person grading one
    work should be able to make mid-review.

    Rights are a ladder — student < reviewer < methodist < admin — so a
    methodist can also grade. That is deliberate and matches the courses: the
    person who wrote the rubric is the one who reviews the disputed work. The
    ladder is not a claim that the roles are interchangeable, only that each
    step keeps what the one below it could do.
    """

    STUDENT = "student"
    REVIEWER = "reviewer"
    METHODIST = "methodist"
    ADMIN = "admin"


class SubmissionStatus(StrEnum):
    """Subset of the architecture's state machine (§10) that the API drives.

    `received` / `normalized` / `scrubbed` collapse into the single
    synchronous `/review` call — there is no queue on the ingest path to
    pause between them. `analyzing` exists for the one thing that *is*
    queued: `review/rerun`.
    """

    DRAFT_READY = "draft_ready"
    ANALYZING = "analyzing"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    FAILED = "failed"


class AuthorType(StrEnum):
    AI = "ai"
    HUMAN = "human"
    AI_ASSISTED = "ai_assisted"


class ChatRole(StrEnum):
    """One entry in a submission's chat transcript.

    `tool` messages are kept, not discarded once used: the reviewer can
    expand "what did it look at" in the transcript, which is the whole point
    of a grounded assistant over a black-box one.
    """

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[Role] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())


class Course(Base):
    """Направление обучения. Рубрики к нему не привязаны — они файлы.

    Курс здесь только чтобы потоки было к чему подвесить и чтобы у статистики
    была верхняя группировка. Всё содержательное про задание живёт в рубрике.
    """

    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    """Человекочитаемый идентификатор: `go`, `system-design`. Совпадает с тем,
    что ревьюеры перечисляют в `course_ids` своих карточек."""
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())

    streams: Mapped[list[Stream]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Stream.key"
    )


class Stream(Base):
    """Поток — конкретный запуск курса, с которым и работают люди.

    Ревьюеров назначают на поток, дедлайны ставят на поток, статистику
    считают по потоку. Курс без потока не проводится.
    """

    __tablename__ = "streams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    """`go-a`, `qa-a`. Уникален в пределах курса, не глобально."""
    title: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="streams")
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="Assignment.created_at"
    )

    __table_args__ = (UniqueConstraint("course_id", "key", name="uq_streams_course_key"),)


class Assignment(Base):
    """Рубрика, выданная потоку в срок. Именно её сдаёт студент.

    Здесь проходит шов, ради которого сущность и заведена: **рубрика — это
    требования, задание — это расписание**. Одна рубрика обслуживает
    несколько потоков, а сроки у них разные, и класть дату в рубрику значило
    бы либо копировать её на каждый поток, либо переписывать файл, по
    которому уже проверены работы.

    До этого дедлайн вбивал ревьюер руками в форме проверки — на каждой
    работе заново. Одна опечатка в дате давала штраф за просрочку там, где
    просрочки не было, и объяснить такой балл студенту было нечем.
    """

    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    stream_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("streams.id"), index=True)
    rubric_key: Mapped[str] = mapped_column(String(128), index=True)
    """`Rubric.assignment_id` — ключ каталога рубрик, который лежит файлами."""
    title: Mapped[str] = mapped_column(String(200), default="")
    """Пусто — берём название из рубрики. Поле для случая, когда поток
    называет то же задание иначе."""
    description: Mapped[str] = mapped_column(default="")
    """Что методист говорит студентам сверх рубрики: где брать данные, как
    оформлять сдачу. В модель не уходит — это не критерий."""

    opens_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)
    """`None` — срока нет, и просрочки не бывает. Это не «забыли заполнить»:
    у восьми курсов из одиннадцати сроков в условиях нет вовсе, и выдумывать
    их за методиста нельзя."""

    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TZ_DATETIME, server_default=func.now(), onupdate=func.now()
    )

    stream: Mapped[Stream] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("stream_id", "rubric_key", name="uq_assignments_stream_rubric"),
    )


class Enrollment(Base):
    """Студент в потоке. Пара, а не поле у пользователя: курсов у него много."""

    __tablename__ = "enrollments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    stream_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("streams.id"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("stream_id", "student_id", name="uq_enrollments_stream_student"),
    )


class Submission(Base):
    """One run of the pipeline the reviewer can come back to.

    `bundle` / `files` / `draft` / `detection` are the exact response bodies
    `/review` and `/detect` already return (`SubmissionBundle`, a list of
    `ArtifactTextOut`, `ReviewDraft`, `DetectionReport`) — stored as JSON so
    `GET /submissions/{id}` and a rerun can rebuild the same Pydantic models
    without re-ingesting from GitHub.
    """

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    origin_url: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(32))
    rubric_key: Mapped[str] = mapped_column(String(128), index=True)
    """`Rubric.assignment_id` — the catalogue key, e.g. `"go-task1"`."""
    status: Mapped[SubmissionStatus] = mapped_column(
        String(16), default=SubmissionStatus.DRAFT_READY
    )

    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assignments.id"), nullable=True, index=True
    )
    """Какое задание сдано. `None` — разбор по ссылке вне потока: рубрику
    назвали напрямую, срока нет. Такой путь остаётся: он нужен, чтобы
    проверить работу до того, как заведён поток."""

    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    """Автор работы, если он завёден аккаунтом. Имени в бандле нет намеренно,
    поэтому связь идёт по строке `users`, а не по тексту сдачи."""

    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)

    bundle: Mapped[dict] = mapped_column(JSON)
    files: Mapped[list] = mapped_column(JSON)
    draft: Mapped[dict] = mapped_column(JSON)
    detection: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rubric_snapshot: Mapped[dict] = mapped_column(JSON)
    """The `Rubric` used to score, frozen at creation time.

    A patch or a rerun scores against *this*, never a fresh catalogue lookup:
    if a methodist edits `rubric_key`'s JSON file afterwards, an already-drafted
    submission must keep meaning what it meant when the model saw it.
    """
    condition_text: Mapped[str] = mapped_column(default="")
    """Kept only so a rerun's prompt matches the original — never the student's name."""

    submitted_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(_TZ_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        _TZ_DATETIME, server_default=func.now(), onupdate=func.now()
    )

    revisions: Mapped[list[ReviewRevision]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="ReviewRevision.created_at"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        cascade="all, delete-orphan", order_by="ChatMessage.seq"
    )


class ReviewRevision(Base):
    """One edit to a draft, with authorship — the audit trail the doc requires (§0, §10).

    `diff` holds whatever changed (criterion id -> {before, after}), not a
    full snapshot: the point is showing a reviewer what a patch did, not
    reconstructing history from scratch.
    """

    __tablename__ = "review_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    author_type: Mapped[AuthorType] = mapped_column(String(16))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    diff: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())

    submission: Mapped[Submission] = relationship(back_populates="revisions")


class ChatMessage(Base):
    """One turn of the reviewer ↔ model conversation over a submission (§6.3).

    `tool_name` is set only on `role="tool"` rows — the result a tool call
    returned, kept so the transcript can show a reviewer what the model
    actually looked at, not just what it concluded.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    seq: Mapped[int] = mapped_column(default=0)
    """Порядок реплики внутри сдачи. Сортировать по `created_at` нельзя.

    Один ход пишет несколько строк — реплику ревьюера, вызовы тулов, ответ, —
    и все они попадают в одну транзакцию. `server_default=now()` в Postgres
    возвращает время *транзакции*, поэтому у всех строк хода метка совпадает
    до микросекунды, а в SQLite гранулярность и вовсе секундная. Сортировка по
    времени в обоих случаях вырождается в произвольную, и транскрипт
    перемешивается ровно там, где порядок и есть смысл: «модель прочитала
    файл, потом ответила» превращается в «ответила, потом прочитала».
    """
    role: Mapped[ChatRole] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(default="")
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_patch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """`propose_review_patch`'s output, if this turn made one — the reviewer
    applies it through the same `PATCH /submissions/{id}/review` any manual
    edit uses; the model never writes the draft directly."""
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())
