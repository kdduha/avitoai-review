from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from avito_reviewer import __version__
from avito_reviewer.ai import AIService
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.auth import seed_users
from avito_reviewer.app.routers import (
    auth_router,
    base_router,
    ingest_router,
    review_router,
    submissions_router,
    users_router,
)
from avito_reviewer.config import AppConfig
from avito_reviewer.db import make_engine, make_sessionmaker, run_migrations
from avito_reviewer.ingest import IngestService
from avito_reviewer.logsetup import configure_logging

_DESCRIPTION = """\
Backend for the Avito AI Reviewer: ingestion, review and AI-detection.

**Auth.** `POST /auth/login` exchanges one of three seeded accounts for a
bearer JWT — `student` / `reviewer` / `admin`, one hardcoded login per role
for the hackathon timeline (see `AuthConfig`). Paste the token into Swagger's
**Authorize** button to call anything below marked 🔒.

**Privacy.** Every model call goes through `PrivacyGateway`: PII is
pseudonymised before it leaves the process and rehydrated only in responses
that stay inside the perimeter. No raw prompt is ever persisted — the audit
log keeps a hash, not the text.

**Scoring.** The model never computes a final score. It answers one rubric
criterion at a time and must cite a quote; the quote is checked against the
file text in code, and the total is summed by a deterministic aggregator.
"""
_TAGS = [
    {"name": "base", "description": "Liveness and startup introspection. No auth."},
    {
        "name": "auth",
        "description": "Exchange a seeded login for a bearer token, and see whose it is.",
    },
    {"name": "ingest", "description": "Turn a submission link into a canonical bundle. 🔒 reviewer+"},
    {
        "name": "review",
        "description": (
            "Grade a submission against a rubric, screen it for generative-AI signs, and "
            "manage the rubric catalogue. 🔒 reviewer+ (rubric compile/confirm/delete and cost: admin+)"
        ),
    },
    {
        "name": "submissions",
        "description": (
            "The persisted half of the pipeline: queues, cards, manual edits with authorship, "
            "approval, reruns, detection verdicts, reassignment, chat. "
            "🔒 reviewer+ (reassign, delete: admin+)"
        ),
    },
    {
        "name": "users",
        "description": "Account CRUD — add a second reviewer to test with, change a role, remove one. 🔒 admin+",
    },
]
_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = AppConfig()
    ingest = IngestService(config.ingest)
    engine = make_engine(config.db)
    sessionmaker = make_sessionmaker(engine)

    app.state.ingest = ingest
    app.state.rubrics = RubricStore(config.ai.rubrics_dir)
    app.state.auth_config = config.auth
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    # Шлюз один на приложение: он держит журнал обращений, и разведение его по
    # запросам потеряло бы сводку по стоимости прогона. Резолвер тел файлов —
    # тот же ingest: схемы `content_ref` знает только он.
    app.state.ai = AIService(config.ai, resolver=ingest)

    # `run_migrations` (Alembic) drives its own event loop internally — it
    # has to leave this one, or "asyncio.run() cannot be called from a
    # running event loop". `create_all` is gone: the schema now has exactly
    # one source of truth, `migrations/versions/`.
    await run_in_threadpool(run_migrations)
    async with sessionmaker() as session:
        await seed_users(session, config.auth)

    _log.info(
        "startup: ingest sources=%s, llm=%s, rubrics=%s",
        [s.value for s in ingest.sources],
        config.ai.llm.provider,
        app.state.rubrics.ids or "none",
    )
    try:
        yield
    finally:
        await ingest.aclose()
        await engine.dispose()
        _log.info("shutdown: ingest closed")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Avito AI Reviewer",
        version=__version__,
        description=_DESCRIPTION,
        openapi_tags=_TAGS,
        lifespan=lifespan,
    )
    app.include_router(base_router)
    app.include_router(auth_router)
    app.include_router(ingest_router)
    app.include_router(review_router)
    app.include_router(submissions_router)
    app.include_router(users_router)
    return app


app = create_app()
