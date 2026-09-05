"""Общее для роутеров: то, что делает больше одна ручка.

Сюда же придёт `get_current_user`, когда появится аутентификация, — роутеры
уже будут брать зависимости отсюда.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from avito_reviewer.app.schemas.review import SubmissionRequest
from avito_reviewer.ingest import (
    IngestContext,
    IngestService,
    InvalidLinkError,
    ProviderFetchError,
    SubmissionBundle,
    UnknownSourceError,
)


async def ingest_submission(request: Request, body: SubmissionRequest) -> SubmissionBundle:
    """Сдача по ссылке. ``422`` — ссылка или источник неверны, ``502`` — источник не ответил."""
    service: IngestService = request.app.state.ingest
    context = IngestContext(
        assignment_id=body.assignment_id,
        deadline_at=body.deadline_at,
        student_internal_id=body.student_internal_id,
    )
    try:
        return await service.ingest(body.link, body.source, context=context)
    except (UnknownSourceError, InvalidLinkError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
