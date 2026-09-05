"""The one queued job: `POST /submissions/{id}/review/rerun`.

Everything else on the request path is synchronous by design (see
`ai/service.py`'s module docstring on why `review`/`detect` stay sync) — a
rubric-sized LLM run is seconds, and queuing it would only add latency for no
benefit. Rerun is different: the architecture explicitly calls it out as its
own step (§11, `POST /submissions/{id}/review/rerun`), separate from the
initial `/review` call, so it is the one place `arq` earns the Redis
dependency instead of sitting in docker-compose unused.

Run the worker with:

    uv run arq avito_reviewer.queue.WorkerSettings

It builds its own `IngestService`: `ai.prepare(bundle)` re-resolves any
`content_ref` the first pass left unfetched, and only that resolver knows how.
It does *not* need `rubrics/` — a rerun re-scores against the rubric frozen
onto the submission at creation time (`Submission.rubric_snapshot`), not a
fresh catalogue lookup, so an edit to the rubric file after the fact cannot
change what an already-drafted submission means.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, ClassVar

from arq.connections import RedisSettings
from fastapi.concurrency import run_in_threadpool

from avito_reviewer.ai import AIService, Rubric
from avito_reviewer.config import AppConfig, QueueConfig
from avito_reviewer.db import (
    Submission,
    SubmissionStatus,
    make_engine,
    make_sessionmaker,
    run_migrations,
)
from avito_reviewer.ingest import IngestService, SubmissionBundle

log = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    config = AppConfig()
    ingest = IngestService(config.ingest)
    engine = make_engine(config.db)
    # Idempotent, and cheap once at head: a safety net for whichever of
    # backend/worker happens to win the race on a cold docker-compose start,
    # not this process's real job (the API owns migrations day to day).
    await run_in_threadpool(run_migrations)
    ctx["ai"] = AIService(config.ai, resolver=ingest)
    ctx["ingest"] = ingest
    ctx["sessionmaker"] = make_sessionmaker(engine)
    ctx["engine"] = engine
    log.info("worker: ready (llm=%s)", config.ai.llm.provider)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["ingest"].aclose()
    await ctx["engine"].dispose()


async def rerun_review(ctx: dict[str, Any], submission_id: str) -> str:
    """Re-run the review agent over a submission's already-ingested bundle.

    No re-fetch of the PR itself: the bundle was stored by the original
    `/review` call, so a rerun only re-asks the model — the reason a
    reviewer asks for one (a flaky first pass), not a change upstream (that
    is what calling `/review` again is for).
    """
    ai: AIService = ctx["ai"]
    sessionmaker = ctx["sessionmaker"]

    async with sessionmaker() as session:
        submission = await session.get(Submission, uuid.UUID(submission_id))
        if submission is None:
            log.warning("rerun: submission %s vanished before the job ran", submission_id)
            return "missing"

        rubric = Rubric.model_validate(submission.rubric_snapshot)
        bundle = SubmissionBundle.model_validate(submission.bundle)
        texts = await ai.prepare(bundle)

        # `AIService.review` reads `submitted_at`/`deadline_at` off `bundle`
        # itself (see `ai/service.py`) — only `condition_text` needs restoring here.
        draft = ai.review(bundle, texts, rubric, condition_text=submission.condition_text)

        # A model call takes seconds; a reviewer can patch or approve in that
        # window. Re-checking status right before the write is what stops a
        # slow rerun from silently overwriting a human edit that landed while
        # it was in flight — first-run "queue it and move on" would otherwise
        # be a trap the moment two things happen to the same submission at once.
        await session.refresh(submission)
        if submission.status != SubmissionStatus.ANALYZING:
            log.warning(
                "rerun: submission %s changed to %s while the job ran — draft kept as-is",
                submission_id, submission.status,
            )
            return "superseded"

        submission.draft = draft.model_dump(mode="json")
        submission.status = SubmissionStatus.DRAFT_READY
        await session.commit()

    log.info("rerun: submission %s refreshed", submission_id)
    return "done"


class WorkerSettings:
    # arq's CLI reads this class's `__dict__` directly (`arq.worker.get_kwargs`)
    # and forwards matching keys straight into `Worker(**kwargs)` — `redis_settings`
    # has to already be a `RedisSettings` instance here, not a method to call.
    functions: ClassVar = [rerun_review]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(QueueConfig().redis_dsn)
