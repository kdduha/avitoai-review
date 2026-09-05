from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from avito_reviewer.app.auth import RequireReviewer
from avito_reviewer.app.schemas.ingest import IngestRequest
from avito_reviewer.ingest import (
    IngestContext,
    IngestService,
    InvalidLinkError,
    ProviderFetchError,
    SubmissionBundle,
    UnknownSourceError,
)

_log = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


@router.post(
    "/ingest",
    summary="Fetch a submission and return its canonical bundle",
    response_description="The canonical SubmissionBundle for the linked submission",
)
async def ingest_submission(body: IngestRequest, request: Request, user: RequireReviewer) -> SubmissionBundle:
    """Resolve ``source`` to a provider, fetch the submission behind ``link`` and
    return the ``SubmissionBundle``: the change under review plus a compact repo map,
    sized to hand to an LLM. Full file bodies are not inlined — an agent pulls them
    later via ``Artifact.content_ref``.

    ``422`` — link malformed or source unknown. ``502`` — the provider's upstream failed.
    """
    service: IngestService = request.app.state.ingest
    context = IngestContext(
        assignment_id=body.assignment_id,
        deadline_at=body.deadline_at,
        student_internal_id=body.student_internal_id,
    )
    try:
        bundle = await service.ingest(body.link, body.source, context=context)
    except (UnknownSourceError, InvalidLinkError) as exc:
        _log.warning("ingest rejected: %s (%s) — %s", body.link, body.source, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderFetchError as exc:
        _log.warning("ingest upstream failed: %s (%s) — %s", body.link, body.source, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    repo_files = len(bundle.repo.files) if bundle.repo else 0
    truncated = " (repo truncated)" if bundle.repo and bundle.repo.truncated else ""
    _log.info(
        "ingested %s — %d artifacts, %d revisions, %d repo files%s",
        body.link,
        len(bundle.artifacts),
        len(bundle.revisions),
        repo_files,
        truncated,
    )
    return bundle
