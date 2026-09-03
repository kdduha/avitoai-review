from __future__ import annotations

from fastapi import APIRouter, Request

from avito_reviewer import __version__
from avito_reviewer.app.schemas.base import HealthResponse, InitResponse
from avito_reviewer.ingest import IngestService

router = APIRouter(tags=["base"])


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    """Return ``ok`` while the process is running. Touches no dependencies."""
    return HealthResponse(status="ok")


@router.get("/init", summary="Startup status")
async def init(request: Request) -> InitResponse:
    """Service version and the ingest providers wired at startup."""
    ingest: IngestService = request.app.state.ingest
    return InitResponse(service="avito-reviewer", version=__version__, sources=ingest.sources)
