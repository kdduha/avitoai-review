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

from sqlalchemy import DateTime, ForeignKey, JSON, String
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
    """RBAC roles: three, not the four in the architecture doc (§2).

    The doc splits `coordinator` (runs the stream: reassign, rubrics, cost)
    from `admin` (config, integrations). One project, one methodist, no
    separate coordinator headcount yet — `admin` does both jobs until that
    split earns its own account. `student` has no API surface today (per the
    doc: "в MVP не имеет UI") — the value exists so a seeded account and a
    future student-facing token are representable, not because any route
    checks for it yet.
    """

    STUDENT = "student"
    REVIEWER = "reviewer"
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
        cascade="all, delete-orphan", order_by="ChatMessage.created_at"
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
    role: Mapped[ChatRole] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(default="")
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_patch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """`propose_review_patch`'s output, if this turn made one — the reviewer
    applies it through the same `PATCH /submissions/{id}/review` any manual
    edit uses; the model never writes the draft directly."""
    created_at: Mapped[datetime] = mapped_column(_TZ_DATETIME, server_default=func.now())
