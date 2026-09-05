"""`rerun_review` — the one arq job — exercised directly, no Redis involved.

`ctx` is exactly what `queue.startup` would put there; building it by hand
here means the job's own logic is tested without going through a real worker
process or a running broker.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from factories import go_bundle, go_rubric

from avito_reviewer.ai import AIService
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.config import AIConfig
from avito_reviewer.db import (
    Submission,
    SubmissionStatus,
    init_models,
    make_engine,
    make_sessionmaker,
)
from avito_reviewer.queue import rerun_review

VERDICTS = json.dumps(
    {
        "verdicts": [
            {"criterion_id": cid, "score": 1, "confidence": 0.9, "verdict": f"{cid} готово",
             "evidence": [], "needs_human_attention": True, "attention_reason": "нет цитаты"}
            for cid in ("c1", "c2", "c3")
        ]
    },
    ensure_ascii=False,
)


class StubResolver:
    async def fetch_content(self, content_ref):
        return None


@pytest.fixture
def ctx(tmp_path):
    async def build():
        from avito_reviewer.config import DatabaseConfig

        engine = make_engine(DatabaseConfig(dsn=f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}"))
        await init_models(engine)
        sessionmaker = make_sessionmaker(engine)
        gateway, provider = fake_gateway([VERDICTS, VERDICTS])
        ai = AIService(AIConfig(), gateway=gateway, resolver=StubResolver())
        return {"ai": ai, "sessionmaker": sessionmaker, "engine": engine}, provider

    context, provider = asyncio.run(build())
    yield context, provider
    asyncio.run(context["engine"].dispose())


def _seed(sessionmaker, *, status=SubmissionStatus.ANALYZING):
    bundle = go_bundle()
    rubric = go_rubric()

    async def insert():
        async with sessionmaker() as session:
            submission = Submission(
                id=bundle.submission_id,
                origin_url=bundle.origin_url,
                source=bundle.source.value,
                rubric_key=rubric.assignment_id,
                rubric_snapshot=rubric.model_dump(mode="json"),
                bundle=bundle.model_dump(mode="json"),
                files=[],
                draft={"assignment_id": rubric.assignment_id, "score": 0.0, "max_score": rubric.scale.total_max,
                       "verdicts": []},
                status=status,
                submitted_at=bundle.submitted_at,
                deadline_at=bundle.deadline_at,
            )
            session.add(submission)
            await session.commit()
        return submission.id

    return asyncio.run(insert())


def test_rerun_refreshes_the_draft_and_marks_it_ready(ctx):
    context, provider = ctx
    submission_id = _seed(context["sessionmaker"])

    result = asyncio.run(rerun_review(context, str(submission_id)))
    assert result == "done"

    async def fetch():
        async with context["sessionmaker"]() as session:
            return await session.get(Submission, submission_id)

    submission = asyncio.run(fetch())
    assert submission.status == SubmissionStatus.DRAFT_READY
    assert submission.draft["score"] > 0
    # Два вызова: критерии и следом итоговый отзыв. Проверяем, что модель
    # позвали заново, а не что она позвана ровно однажды.
    assert len(provider.calls) == 2


def test_rerun_on_a_vanished_submission_is_reported_not_raised(ctx):
    import uuid

    context, _ = ctx
    result = asyncio.run(rerun_review(context, str(uuid.uuid4())))
    assert result == "missing"


def test_rerun_does_not_clobber_a_human_edit_made_while_it_ran(ctx):
    """A reviewer can patch or approve while a rerun is still talking to the
    model — the job must notice its target moved and keep the human edit."""
    context, _ = ctx
    submission_id = _seed(context["sessionmaker"], status=SubmissionStatus.ANALYZING)

    async def patch_mid_flight():
        async with context["sessionmaker"]() as session:
            submission = await session.get(Submission, submission_id)
            # Reassign, don't mutate in place: a plain `submission.draft["score"]
            # = ...` never marks the JSON column dirty, so SQLAlchemy would skip
            # the UPDATE entirely and this test would pass for the wrong reason.
            submission.draft = {**submission.draft, "score": 99.0}
            submission.status = SubmissionStatus.IN_REVIEW
            await session.commit()

    asyncio.run(patch_mid_flight())
    result = asyncio.run(rerun_review(context, str(submission_id)))
    assert result == "superseded"

    async def fetch():
        async with context["sessionmaker"]() as session:
            return await session.get(Submission, submission_id)

    submission = asyncio.run(fetch())
    assert submission.status == SubmissionStatus.IN_REVIEW
    assert submission.draft["score"] == 99.0
