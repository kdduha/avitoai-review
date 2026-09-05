from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from avito_reviewer import __version__
from avito_reviewer.ai import AIService
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.routers import (
    base_router,
    distribution_router,
    ingest_router,
    review_router,
)
from avito_reviewer.config import AIConfig, IngestConfig
from avito_reviewer.distribution import ReviewerStore
from avito_reviewer.ingest import IngestService
from avito_reviewer.logsetup import configure_logging

_DESCRIPTION = "Backend for the Avito AI Reviewer: ingestion, review and AI-detection."
_TAGS = [
    {"name": "base", "description": "Liveness and startup introspection."},
    {"name": "ingest", "description": "Turn a submission link into a canonical bundle."},
    {
        "name": "review",
        "description": "Grade a submission against a rubric and screen it for generative-AI signs.",
    },
    {
        "name": "distribution",
        "description": "Profile a submission and lay a batch of them out across reviewers.",
    },
]
_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    ai_config = AIConfig()
    ingest = IngestService(IngestConfig())

    app.state.ingest = ingest
    app.state.rubrics = RubricStore(ai_config.rubrics_dir)
    app.state.reviewers = ReviewerStore(ai_config.reviewers_dir)
    # Шлюз один на приложение: он держит журнал обращений, и разведение его по
    # запросам потеряло бы сводку по стоимости прогона. Резолвер тел файлов —
    # тот же ingest: схемы `content_ref` знает только он.
    app.state.ai = AIService(ai_config, resolver=ingest)

    _log.info(
        "startup: ingest sources=%s, llm=%s, rubrics=%s, reviewers=%s",
        [s.value for s in ingest.sources],
        ai_config.llm.provider,
        app.state.rubrics.ids or "none",
        len(app.state.reviewers.ids) or "none",
    )
    try:
        yield
    finally:
        await ingest.aclose()
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
    app.include_router(ingest_router)
    app.include_router(review_router)
    app.include_router(distribution_router)
    return app


app = create_app()
