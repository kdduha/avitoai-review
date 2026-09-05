from __future__ import annotations

from fastapi import APIRouter, Request

from avito_reviewer import __version__
from avito_reviewer.ai import AIService
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.schemas.base import HealthResponse, InitResponse
from avito_reviewer.distribution import ReviewerStore
from avito_reviewer.ingest import IngestService

router = APIRouter(tags=["base"])


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    """Return ``ok`` while the process is running. Touches no dependencies."""
    return HealthResponse(status="ok")


@router.get("/init", summary="Startup status")
async def init(request: Request) -> InitResponse:
    """Service version, the ingest providers wired at startup, and the model route."""
    ingest: IngestService = request.app.state.ingest
    ai: AIService = request.app.state.ai
    rubrics: RubricStore = request.app.state.rubrics
    reviewers: ReviewerStore = request.app.state.reviewers
    return InitResponse(
        service="avito-reviewer",
        version=__version__,
        sources=ingest.sources,
        llm_provider=ai.config.llm.provider,
        llm_model=ai.config.llm.model,
        rubrics=rubrics.ids,
        reviewers=reviewers.ids,
    )
