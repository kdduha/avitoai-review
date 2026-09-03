from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from avito_reviewer import __version__
from avito_reviewer.app.routers import base_router, ingest_router
from avito_reviewer.config import IngestConfig
from avito_reviewer.ingest import IngestService
from avito_reviewer.logsetup import configure_logging

_DESCRIPTION = "Backend for the Avito AI Reviewer: ingestion, review and AI-detection."
_TAGS = [
    {"name": "base", "description": "Liveness and startup introspection."},
    {"name": "ingest", "description": "Turn a submission link into a canonical bundle."},
]
_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.ingest = IngestService(IngestConfig())
    _log.info("startup: ingest ready, sources=%s", [s.value for s in app.state.ingest.sources])
    try:
        yield
    finally:
        await app.state.ingest.aclose()
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
    return app


app = create_app()
