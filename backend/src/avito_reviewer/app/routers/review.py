from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from avito_reviewer.ai import AIService, Rubric
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.schemas.review import (
    ArtifactTextOut,
    CostSummary,
    DetectRequest,
    DetectResponse,
    ReviewRequest,
    ReviewResponse,
    RubricSummary,
)
from avito_reviewer.ingest import (
    IngestContext,
    IngestService,
    InvalidLinkError,
    ProviderFetchError,
    SubmissionBundle,
    UnknownSourceError,
)

_log = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


async def _ingest(request: Request, body: DetectRequest | ReviewRequest) -> SubmissionBundle:
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


def _rubric(request: Request, rubric_id: str | None, inline: Rubric | None) -> Rubric:
    if inline is not None:
        return inline
    store: RubricStore = request.app.state.rubrics
    rubric = store.get(rubric_id or "")
    if rubric is None:
        raise HTTPException(
            status_code=404,
            detail=f"рубрика {rubric_id!r} не найдена; доступны: {', '.join(store.ids) or '—'}",
        )
    return rubric


@router.get("/rubrics", summary="Rubrics available to review against")
async def list_rubrics(request: Request) -> list[RubricSummary]:
    """Каталог рубрик. Добавить курс — значит положить рядом ещё один JSON."""
    store: RubricStore = request.app.state.rubrics
    return [RubricSummary.of(store.get(rubric_id)) for rubric_id in store.ids]  # type: ignore[arg-type]


@router.get("/rubrics/{assignment_id}", summary="One rubric in full")
async def get_rubric(assignment_id: str, request: Request) -> Rubric:
    """Критерии, якоря и шкала — то, против чего ставился каждый вердикт."""
    return _rubric(request, assignment_id, None)


@router.post("/review", summary="Draft a review of a submission against a rubric")
async def review(body: ReviewRequest, request: Request) -> ReviewResponse:
    """Собрать сдачу по ссылке и вернуть черновик ревью с проверенными цитатами.

    Балл считает код, а не модель: она отвечает по каждому критерию отдельно и
    обязана приложить цитату, которая затем сверяется с текстом файла.
    Вердикты без подтверждённой цитаты помечены `needs_human_attention`.

    ``404`` — рубрика не найдена. ``422`` — ссылка или источник неверны.
    ``502`` — источник сдачи не ответил.
    """
    rubric = _rubric(request, body.rubric_id, body.rubric)
    bundle = await _ingest(request, body)

    ai: AIService = request.app.state.ai
    texts = await ai.prepare(bundle)
    # Слой синхронный: считает, парсит и ходит к модели по HTTP блокирующе.
    # Держать на нём событийный цикл нельзя, переписывать ради этого на async
    # незачем — выигрыш нулевой, а поверхность для ошибок заметная.
    draft = await run_in_threadpool(
        ai.review,
        bundle,
        texts,
        rubric,
        gate_facts=body.gate_facts,
        condition_text=body.condition_text,
    )
    return ReviewResponse(
        bundle=bundle,
        files=[ArtifactTextOut.of(text) for text in texts],
        draft=draft,
    )


@router.post("/detect", summary="Look for signs of generative-AI authorship")
async def detect(body: DetectRequest, request: Request) -> DetectResponse:
    """Ансамбль из четырёх сигналов: форензика истории, стилометрия, перплексия, judge.

    Вывод рекомендательный. Он не является доказательством, на балл не влияет
    и содержит явный список того, чего проверка не видела: недоступные сигналы
    и файлы, доступные только фрагментом.
    """
    rubric = (
        _rubric(request, body.rubric_id, None) if body.rubric_id else None
    )
    bundle = await _ingest(request, body)

    ai: AIService = request.app.state.ai
    texts = await ai.prepare(bundle)
    report = await run_in_threadpool(ai.detect, bundle, texts, rubric)
    return DetectResponse(
        bundle=bundle,
        files=[ArtifactTextOut.of(text) for text in texts],
        report=report,
    )


@router.get("/cost", summary="Model spend since startup")
async def cost(request: Request) -> CostSummary:
    """Журнал шлюза в цифрах: сколько вызовов ушло наружу, сколько это стоило."""
    ai: AIService = request.app.state.ai
    return CostSummary.model_validate(ai.cost_summary)
