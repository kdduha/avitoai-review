from __future__ import annotations

import logging
from functools import partial

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from avito_reviewer.ai import AIService
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.auth import RequireReviewer
from avito_reviewer.app.deps import ingest_submission
from avito_reviewer.app.schemas.distribution import (
    DistributeRequest,
    WorkProfileRequest,
    WorkProfileResponse,
)
from avito_reviewer.config import AIConfig
from avito_reviewer.distribution import DistributionPlan, Reviewer, ReviewerStore, distribute
from avito_reviewer.distribution.profile import ProfileError, WorkProfiler, item_for
from avito_reviewer.ingest import IngestService

_log = logging.getLogger(__name__)

router = APIRouter(tags=["distribution"])


@router.post("/work-profile", summary="Describe a submission and estimate the review effort")
async def work_profile(
    body: WorkProfileRequest, request: Request, user: RequireReviewer
) -> WorkProfileResponse:
    """Собрать профиль работы: о чём она и сколько займёт её проверка.

    Единственный вызов модели во всём распределении. Дальше решает код:
    `/distribute` к модели не ходит вовсе, потому что координатор обязан уметь
    объяснить студенту, почему его проверяет именно этот человек, а
    вероятностный ответ на такой вопрос не годится.

    Оценка минут обрезается потолком, и обрезание видно в `profile.warnings`:
    солвер верит ей как факту, и ошибка на порядок молча съела бы ёмкость всего
    потока.

    ``404`` — рубрика не найдена. ``422`` — ссылка или источник неверны.
    ``502`` — источник сдачи или модель не ответили.
    """
    rubric = None
    if body.rubric_id:
        store: RubricStore = request.app.state.rubrics
        rubric = store.get(body.rubric_id)
        if rubric is None:
            raise HTTPException(
                status_code=404,
                detail=f"рубрика {body.rubric_id!r} не найдена; доступны: "
                f"{', '.join(store.ids) or '—'}",
            )

    bundle = await ingest_submission(request, body)
    ai: AIService = request.app.state.ai
    texts = await ai.prepare(bundle)
    config: AIConfig = ai.config

    try:
        profile = await run_in_threadpool(
            partial(
                WorkProfiler(ai.gateway).profile,
                bundle,
                texts,
                rubric=rubric,
                condition_text=body.condition_text,
                identities=ai.identities(bundle, body.student_name),
                max_review_minutes=config.distribution.max_review_minutes,
            )
        )
    except ProfileError as exc:
        _log.warning("профиль %s не собран: %s", body.link, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return WorkProfileResponse(
        profile=profile,
        item=item_for(
            bundle,
            profile,
            assignment_id=body.rubric_id or "",
        ),
    )


@router.post("/distribute", summary="Lay submissions out across reviewers")
async def distribute_submissions(
    body: DistributeRequest, request: Request, user: RequireReviewer
) -> DistributionPlan:
    """Разложить работы по ревьюерам и объяснить каждое назначение.

    К модели не обращается ни разу: раскладка не стоит ни одного токена и
    воспроизводима — один и тот же пул даёт побитово один и тот же план, иначе
    координатор, увидевший в 10:00 и в 10:05 разное, перестанет ей пользоваться.

    Исчерпание ёмкости — это результат, а не ошибка: работы, которые никто не
    смог взять, приходят в `unassigned` с поимённым списком отказавших.

    ``404`` — распределять не между кем: пул не передан, а каталог пуст.
    ``422`` — пустой или противоречивый пул, либо `reviewer_ids` с идентификатором,
    которого в каталоге нет.
    """
    pool = _pool(request, body)
    ingest: IngestService = request.app.state.ingest
    config: AIConfig = request.app.state.ai.config
    limit = (
        body.max_items_per_reviewer
        if body.max_items_per_reviewer is not None
        else config.distribution.max_items_per_reviewer
    )

    return await run_in_threadpool(
        partial(
            distribute,
            body.items,
            pool,
            committed_minutes=body.committed_minutes,
            weights=body.weights,
            now=body.now,
            max_items_per_reviewer=limit,
            alternatives=config.distribution.alternatives,
            author_salt=ingest.author_salt,
        )
    )


def _pool(request: Request, body: DistributeRequest) -> list[Reviewer]:
    if body.reviewers is not None and body.reviewer_ids:
        raise HTTPException(
            status_code=422,
            detail="укажите либо reviewers, либо reviewer_ids: вместе они противоречат друг другу",
        )
    if body.reviewers is not None:
        if not body.reviewers:
            raise HTTPException(status_code=422, detail="пул ревьюеров пуст")
        return body.reviewers

    store: ReviewerStore = request.app.state.reviewers
    if body.reviewer_ids:
        missing = [key for key in body.reviewer_ids if store.get(key) is None]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"нет в каталоге: {', '.join(missing)}; доступны: "
                f"{', '.join(store.ids) or '—'}",
            )
        return [reviewer for key in body.reviewer_ids if (reviewer := store.get(key))]

    pool = store.all()
    if not pool:
        raise HTTPException(
            status_code=404,
            detail=(
                f"каталог ревьюеров пуст ({store.directory}); положите карточки рядом "
                "или передайте пул в запросе"
            ),
        )
    return pool
