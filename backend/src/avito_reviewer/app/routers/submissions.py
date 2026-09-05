"""Submissions: the persisted half of the pipeline.

`/review` and `/detect` (in `review.py`) compute a draft; this router is
where a reviewer comes back to it — a queue, a card, manual edits with
authorship, approval, and the one queued job (`review/rerun`). Everything
here reads or writes a single `Submission` row; there is no second
`SubmissionBundle` fetch anywhere in this file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from avito_reviewer.ai import AIService, ArtifactText, Rubric, run_chat
from avito_reviewer.ai.detection import DetectionReport
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.review.aggregate import aggregate
from avito_reviewer.app.auth import RequireAdmin, RequireReviewer
from avito_reviewer.app.schemas.chat import ChatMessageOut, ChatRequest, ProposedPatchOut
from avito_reviewer.app.schemas.review import ArtifactTextOut
from avito_reviewer.app.schemas.submissions import (
    AuditRecordOut,
    CriterionPatch,
    DetectionVerdictRequest,
    ReassignRequest,
    RerunResponse,
    ReviewPatchRequest,
    SubmissionDetail,
    SubmissionSummary,
)
from avito_reviewer.config import QueueConfig
from avito_reviewer.db import (
    AuthorType,
    ChatMessage,
    ChatRole,
    Role,
    Submission,
    SubmissionStatus,
    User,
    session_dependency,
)
from avito_reviewer.ingest import ArtifactRole, ChangeStatus, SubmissionBundle

router = APIRouter(tags=["submissions"])

Session = Annotated[AsyncSession, Depends(session_dependency)]


async def _load(
    submission_id: UUID, session: AsyncSession, user: User, *, for_write: bool = False
) -> Submission:
    """Fetch a submission and enforce "a reviewer only touches their own queue".

    Admins see and edit anything; a plain reviewer gets 404
    rather than 403 for someone else's submission — a queue is not a place to
    confirm *that* a colleague's work exists, only that yours does.
    """
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="сдача не найдена")
    if Role(user.role) is Role.REVIEWER and submission.reviewer_id != user.id:
        raise HTTPException(status_code=404, detail="сдача не найдена")
    # `submission.status` приходит из SQLAlchemy обычной строкой, не членом
    # перечисления: `is` здесь всегда был бы False. `==` у `StrEnum` сравнивает
    # по значению и работает для обеих форм.
    if for_write and submission.status == SubmissionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="сдача уже утверждена")
    return submission


async def _username(session: AsyncSession, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    return user.username if user else None


async def _summary(session: AsyncSession, submission: Submission) -> SubmissionSummary:
    draft = submission.draft
    return SubmissionSummary(
        id=submission.id,
        origin_url=submission.origin_url,
        assignment_id=submission.rubric_key,
        status=submission.status,
        reviewer_username=await _username(session, submission.reviewer_id),
        score=draft.get("score", 0.0),
        max_score=draft.get("max_score", 0.0),
        passed=draft.get("passed", False),
        needs_human_attention=draft.get("needs_human_attention", False),
        submitted_at=submission.submitted_at,
        deadline_at=submission.deadline_at,
        created_at=submission.created_at,
    )


# --------------------------------------------------------------------------- #
# очередь и карточка
# --------------------------------------------------------------------------- #

@router.get("/me/queue", summary="The current reviewer's queue")
async def my_queue(
    user: RequireReviewer,
    session: Session,
    all_reviewers: Annotated[
        bool, Query(alias="all", description="admin: все сдачи потока, не только свои")
    ] = False,
) -> list[SubmissionSummary]:
    """Submissions assigned to the caller, deadline-soonest first.

    An admin may pass ``?all=true`` to see the whole stream instead of just
    their own queue — the dashboard-shaped view the architecture doc puts
    behind `GET /courses/{id}/dashboard`, without inventing the
    course/assignment-engine machinery that endpoint implies.
    """
    stmt = select(Submission)
    if not (all_reviewers and Role(user.role) is Role.ADMIN):
        stmt = stmt.where(Submission.reviewer_id == user.id)
    stmt = stmt.order_by(Submission.deadline_at.is_(None), Submission.deadline_at)
    submissions = (await session.execute(stmt)).scalars().all()
    return [await _summary(session, s) for s in submissions]


@router.get("/submissions/{submission_id}", summary="Full card of one submission")
async def get_submission(
    submission_id: UUID, user: RequireReviewer, session: Session
) -> SubmissionDetail:
    submission = await _load(submission_id, session, user)
    return SubmissionDetail(
        id=submission.id,
        status=submission.status,
        reviewer_username=await _username(session, submission.reviewer_id),
        approved_by_username=await _username(session, submission.approved_by),
        approved_at=submission.approved_at,
        bundle=SubmissionBundle.model_validate(submission.bundle),
        files=[ArtifactTextOut.model_validate(f) for f in submission.files],
        draft=ReviewDraft.model_validate(submission.draft),
        detection=DetectionReport.model_validate(submission.detection) if submission.detection else None,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
        rubric=Rubric.model_validate(submission.rubric_snapshot),
    )


@router.delete("/submissions/{submission_id}", summary="Remove a submission", status_code=204)
async def delete_submission(submission_id: UUID, admin: RequireAdmin, session: Session) -> None:
    """Admin only — mainly for cleaning up a bad test run. Cascades to its
    `review_revisions` and `chat_messages`; the GitHub PR itself is untouched,
    only this record of having reviewed it."""
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="сдача не найдена")
    await session.delete(submission)
    await session.commit()


@router.get(
    "/submissions/{submission_id}/artifacts/{path:path}",
    summary="One file's text as the model saw it",
)
async def get_artifact(
    submission_id: UUID, path: str, user: RequireReviewer, session: Session
) -> ArtifactTextOut:
    submission = await _load(submission_id, session, user)
    for file in submission.files:
        if file["path"] == path:
            return ArtifactTextOut.model_validate(file)
    raise HTTPException(status_code=404, detail=f"файл {path!r} не входит в разбор этой сдачи")


# --------------------------------------------------------------------------- #
# черновик ревью
# --------------------------------------------------------------------------- #

@router.get("/submissions/{submission_id}/review", summary="Stored review draft")
async def get_review(submission_id: UUID, user: RequireReviewer, session: Session) -> ReviewDraft:
    submission = await _load(submission_id, session, user)
    return ReviewDraft.model_validate(submission.draft)


def _apply_patch(verdict: dict, patch: CriterionPatch) -> dict:
    if patch.score is not None:
        verdict["score"] = patch.score
    if patch.verdict is not None:
        verdict["verdict"] = patch.verdict
    if patch.student_feedback is not None:
        verdict["student_feedback"] = patch.student_feedback
    verdict["needs_human_attention"] = False
    verdict["attention_reason"] = ""
    return verdict


@router.patch("/submissions/{submission_id}/review", summary="Manually override one or more criteria")
async def patch_review(
    submission_id: UUID, body: ReviewPatchRequest, user: RequireReviewer, session: Session
) -> ReviewDraft:
    """Overwrite score/verdict/feedback on named criteria and recompute the total.

    The total is never hand-edited directly — only `review/aggregate.py`
    produces it, from whatever the criteria say now. Every patch is logged to
    `review_revisions` with ``author_type=human`` before/after, per the
    architecture's audit requirement (§0, §10).
    """
    from avito_reviewer.ai.rubric import Rubric
    from avito_reviewer.db import ReviewRevision

    submission = await _load(submission_id, session, user, for_write=True)
    draft = submission.draft
    by_id = {v["criterion_id"]: v for v in draft["verdicts"]}

    diff: dict[str, dict] = {}
    for patch in body.patches:
        current = by_id.get(patch.criterion_id)
        if current is None:
            raise HTTPException(status_code=422, detail=f"нет критерия {patch.criterion_id!r} в черновике")
        before = {"score": current["score"], "verdict": current["verdict"]}
        _apply_patch(current, patch)
        diff[patch.criterion_id] = {"before": before, "after": {"score": current["score"], "verdict": current["verdict"]}}

    # Та же рубрика, что видела модель — не свежий взгляд в каталог: если
    # методист правит JSON после разбора, уже выставленный балл не должен
    # молча пересчитаться по другим весам и порогам.
    rubric = Rubric.model_validate(submission.rubric_snapshot)
    breakdown = aggregate(
        [_verdict_model(v) for v in draft["verdicts"]],
        rubric,
        submitted_at=submission.submitted_at,
        deadline_at=submission.deadline_at,
    )
    draft["raw_score"] = breakdown.raw_score
    draft["score"] = breakdown.final_score
    draft["passed"] = breakdown.passed
    draft["pass_explanation"] = breakdown.pass_explanation

    submission.draft = draft
    # `draft` is the same dict object `submission.draft` already held — mutated
    # in place above, not replaced. SQLAlchemy's plain `JSON` column diffs the
    # reassignment against that identical reference and, finding no difference,
    # silently drops it from the UPDATE. `flag_modified` forces it in anyway.
    flag_modified(submission, "draft")
    submission.status = SubmissionStatus.IN_REVIEW
    session.add(ReviewRevision(submission_id=submission.id, author_type=AuthorType.HUMAN, author_id=user.id, diff=diff))
    await session.commit()
    return ReviewDraft.model_validate(submission.draft)


def _verdict_model(raw: dict):
    from avito_reviewer.ai.review import CriterionVerdict

    return CriterionVerdict.model_validate(raw)


@router.post("/submissions/{submission_id}/review/approve", summary="Approve the draft")
async def approve(submission_id: UUID, user: RequireReviewer, session: Session) -> SubmissionSummary:
    submission = await _load(submission_id, session, user, for_write=True)
    submission.status = SubmissionStatus.APPROVED
    submission.approved_by = user.id
    submission.approved_at = datetime.now(tz=UTC)
    await session.commit()
    return await _summary(session, submission)


@router.post(
    "/submissions/{submission_id}/review/rerun",
    summary="Re-queue the review agent over the stored bundle",
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun(submission_id: UUID, user: RequireReviewer, session: Session) -> RerunResponse:
    """Queue a fresh model pass — the one job that goes through Redis/arq.

    ``503`` — the queue is unreachable. Run the worker with
    ``uv run arq avito_reviewer.queue.WorkerSettings``.
    """
    submission = await _load(submission_id, session, user, for_write=True)

    from arq import create_pool
    from redis.exceptions import RedisError

    try:
        pool = await create_pool(_redis_settings())
        await pool.enqueue_job("rerun_review", str(submission.id))
        await pool.close()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"очередь недоступна: {exc}") from exc

    submission.status = SubmissionStatus.ANALYZING
    await session.commit()
    return RerunResponse(submission_id=submission.id, status=submission.status)


def _redis_settings():
    from arq.connections import RedisSettings

    # `conn_retries=0`: a request should fail fast and tell the reviewer to
    # try again, not hang for the worker-side default of five retries.
    settings = RedisSettings.from_dsn(QueueConfig().redis_dsn)
    settings.conn_retries = 0
    return settings


# --------------------------------------------------------------------------- #
# детектор
# --------------------------------------------------------------------------- #

@router.get("/submissions/{submission_id}/ai-detection", summary="Stored AI-detection report")
async def get_detection(submission_id: UUID, user: RequireReviewer, session: Session) -> DetectionReport:
    submission = await _load(submission_id, session, user)
    if submission.detection is None:
        raise HTTPException(
            status_code=404,
            detail="детектор ещё не запускался — передайте with_detection=true в /review или POST /detect",
        )
    return DetectionReport.model_validate(submission.detection)


@router.post(
    "/submissions/{submission_id}/ai-detection/{span_id}/verdict",
    summary="Reviewer confirms or rejects one detection span",
)
async def set_detection_verdict(
    submission_id: UUID,
    span_id: str,
    body: DetectionVerdictRequest,
    user: RequireReviewer,
    session: Session,
) -> DetectionReport:
    """Advisory only, by design (§7.5): this never touches `score`. It logs a
    reviewer's judgement on one span, which is exactly the labelled data the
    architecture names as the input to future threshold calibration.

    Allowed after approval on purpose — confirming or rejecting a signal is
    not a review edit (§7.5 again: it cannot change the score), so the "no
    writes to an approved submission" guard that blocks `PATCH .../review`
    does not apply here.
    """
    submission = await _load(submission_id, session, user)
    if submission.detection is None:
        raise HTTPException(status_code=404, detail="детектор ещё не запускался")

    report = submission.detection
    for span in report["spans"]:
        if span["id"] == span_id:
            span["reviewer_verdict"] = body.verdict
            break
    else:
        raise HTTPException(status_code=404, detail=f"спан {span_id!r} не найден")

    submission.detection = report
    flag_modified(submission, "detection")  # same reference mutated in place — see patch_review
    await session.commit()
    return DetectionReport.model_validate(submission.detection)


# --------------------------------------------------------------------------- #
# переназначение
# --------------------------------------------------------------------------- #

@router.post("/submissions/{submission_id}/reassign", summary="Hand a submission to another reviewer")
async def reassign(
    submission_id: UUID, body: ReassignRequest, user: RequireAdmin, session: Session
) -> SubmissionSummary:
    """Admin only — the doc's `POST /assignments/{id}/reassign` (§11), scoped
    to one submission rather than an assignment: there is no Assignment
    Engine here to reassign a whole batch by, only rows an admin can move
    one at a time.
    """
    from avito_reviewer.db import ReviewRevision

    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="сдача не найдена")

    target = (
        await session.execute(select(User).where(User.username == body.reviewer_username))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail=f"пользователь {body.reviewer_username!r} не найден")

    submission.reviewer_id = target.id
    session.add(
        ReviewRevision(
            submission_id=submission.id, author_type=AuthorType.HUMAN, author_id=user.id,
            diff={"reassigned_to": body.reviewer_username},
        )
    )
    await session.commit()
    return await _summary(session, submission)


# --------------------------------------------------------------------------- #
# аудит
# --------------------------------------------------------------------------- #

@router.get("/audit/llm-calls", summary="Raw audit log of every model call")
async def audit_llm_calls(user: RequireAdmin, request: Request) -> list[AuditRecordOut]:
    """Everything `GET /cost` totals, one row per call — route, model, tokens,
    cost, and whether it errored. The prompt itself is never in here (see
    `ai/llm/audit.py`): only its hash is, and that is not returned either.
    """
    records = request.app.state.ai.gateway.audit.records
    return [
        AuditRecordOut(
            request_id=r.request_id, provider=r.provider, model=r.model, task=r.task,
            data_class=r.data_class, route=r.route, redactions=r.redactions,
            tokens_in=r.tokens_in, tokens_out=r.tokens_out, latency_ms=r.latency_ms,
            cost_rub=r.cost_rub, error=r.error, at=r.at,
        )
        for r in records
    ]


# --------------------------------------------------------------------------- #
# чат ревьюера с моделью (§6.3)
# --------------------------------------------------------------------------- #

def _texts_from_stored(files: list[dict]) -> list[ArtifactText]:
    """Rebuild the tool-facing `ArtifactText` view from what `/review` stored.

    Lossy on purpose: `status` and `changed` are not preserved in
    `ArtifactTextOut`, and chat tools never read either — only `text`,
    `lines`/`line_numbers` and `partial` do. Rebuilding from the stored row
    means a chat turn touches no network at all, unlike a rerun.
    """
    out = []
    for f in files:
        text = f.get("text") or ""
        out.append(
            ArtifactText(
                path=f["path"],
                role=ArtifactRole(f["role"]),
                status=ChangeStatus.MODIFIED,
                lang=f.get("lang"),
                lines=text.split("\n") if text else [],
                line_numbers=f.get("line_numbers") or [],
                partial=bool(f.get("partial")),
                origin=f.get("origin", "diff"),
            )
        )
    return out


def _chat_history(rows: list[ChatMessage]) -> list[dict[str, str]]:
    """Prior turns fed back to the model — replies only, no tool noise.

    Keeps the prompt bounded to what the agent actually said, not every
    intermediate `get_file` result it asked for along the way (see
    `ai/chat.py`'s module docstring).
    """
    return [
        {"role": "user" if row.role == ChatRole.USER else "assistant", "content": row.content}
        for row in rows
        if row.role in (ChatRole.USER, ChatRole.ASSISTANT)
    ]


def _out(message: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        role=ChatRole(message.role).value,
        content=message.content,
        tool_name=message.tool_name,
        proposed_patch=ProposedPatchOut.model_validate(message.proposed_patch)
        if message.proposed_patch
        else None,
        created_at=message.created_at,
    )


@router.get("/submissions/{submission_id}/chat", summary="Stored chat transcript")
async def get_chat(submission_id: UUID, user: RequireReviewer, session: Session) -> list[ChatMessageOut]:
    await _load(submission_id, session, user)
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.submission_id == submission_id)
            .order_by(ChatMessage.seq)
        )
    ).scalars().all()
    return [_out(row) for row in rows]


@router.post(
    "/submissions/{submission_id}/chat",
    summary="Ask the model about this submission, streamed over SSE",
)
async def chat(
    submission_id: UUID, body: ChatRequest, user: RequireReviewer, session: Session, request: Request
) -> StreamingResponse:
    """One turn of the tool-using chat from architecture §6.3: `get_file`,
    `get_diff`, `get_criterion`, `search_submission`, `propose_review_patch`.

    The model never edits the draft — `propose_review_patch` only returns a
    proposal; applying it is `PATCH /submissions/{id}/review`, the same
    endpoint a manual edit uses. Every step (tool calls, their results, the
    final reply) is persisted before it is streamed, so a dropped connection
    never loses the turn — reload `GET .../chat` and it is there.

    Streaming here means the *transport* is SSE, not that the model's answer
    arrives token by token: the whole turn (all tool calls plus the final
    reply) is computed first, then sent out as a sequence of `data:` events.
    True upstream token streaming is a real future improvement, not something
    this endpoint's contract promises today.
    """
    submission = await _load(submission_id, session, user)
    rubric = Rubric.model_validate(submission.rubric_snapshot)
    draft = ReviewDraft.model_validate(submission.draft)
    texts = _texts_from_stored(submission.files)
    diffs = {
        artifact["path"]: artifact["diff"]
        for artifact in submission.bundle.get("artifacts", [])
        if artifact.get("diff")
    }
    history_rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.submission_id == submission_id)
            .order_by(ChatMessage.seq)
        )
    ).scalars().all()

    # Реплика ревьюера сохраняется ДО обращения к модели. Раньше она писалась
    # после, и любой неожиданный сбой в ходе уносил с собой набранный человеком
    # текст: клиент показывал ошибку, а перезагрузка транскрипта не находила
    # даже вопроса. Вопрос, оставшийся без ответа, — честная картина; вопрос,
    # исчезнувший вместе с ответом, — потеря данных.
    next_seq = len(history_rows)
    session.add(
        ChatMessage(
            submission_id=submission.id,
            seq=next_seq,
            role=ChatRole.USER,
            content=body.message,
        )
    )
    await session.commit()

    ai: AIService = request.app.state.ai
    detection = (
        DetectionReport.model_validate(submission.detection) if submission.detection else None
    )
    steps = await run_in_threadpool(
        run_chat,
        ai.gateway,
        rubric=rubric,
        draft=draft,
        texts=texts,
        diffs=diffs,
        history=_chat_history(list(history_rows)),
        message=body.message,
        detection=detection,
        # Логины студента лежат в бандле, и в `/review` шлюз вычищает их
        # прицельно. Чат ходит в ту же модель по тому же тексту работы —
        # оставлять его на общих детекторах ПДн значит защищать одну дверь
        # из двух.
        identities=AIService.identities(SubmissionBundle.model_validate(submission.bundle)),
    )

    saved: list[ChatMessage] = []
    for offset, step in enumerate(steps, start=1):
        row = ChatMessage(
            submission_id=submission.id,
            seq=next_seq + offset,
            role=ChatRole.TOOL if step.kind == "tool" else ChatRole.ASSISTANT,
            content=step.content,
            tool_name=step.tool_name,
            proposed_patch=step.proposed_patch.model_dump() if step.proposed_patch else None,
        )
        session.add(row)
        saved.append(row)
    await session.commit()

    async def events():
        for row in saved:
            yield f"data: {json.dumps(_out(row).model_dump(mode='json'), ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
