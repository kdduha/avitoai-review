from __future__ import annotations

import logging
from datetime import UTC, datetime
from functools import partial
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.ai import AIService, Rubric
from avito_reviewer.ai.compiler import DRAFT_NOTE, CompilerError, RubricCompiler
from avito_reviewer.ai.content import ArtifactText
from avito_reviewer.ai.detection import DetectionReport
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.rubric import RubricExists, RubricRejected, RubricStore
from avito_reviewer.app.auth import RequireAdmin, RequireMethodist, RequireReviewer
from avito_reviewer.app.deps import ingest_submission
from avito_reviewer.app.schemas.review import (
    ArtifactTextOut,
    CompileRubricRequest,
    CompileRubricResponse,
    ConfirmRubricRequest,
    ConfirmRubricResponse,
    CostSummary,
    DetectRequest,
    DetectResponse,
    ReviewRequest,
    ReviewResponse,
    RubricSummary,
)
from avito_reviewer.db import Assignment, Role, Submission, User, session_dependency
from avito_reviewer.ingest import SubmissionBundle

_log = logging.getLogger(__name__)

router = APIRouter(tags=["review"])

Session = Annotated[AsyncSession, Depends(session_dependency)]


async def _detection(
    ai: AIService,
    bundle: SubmissionBundle,
    texts: list[ArtifactText],
    rubric: Rubric,
    draft: ReviewDraft,
    *,
    student_name: str | None,
) -> DetectionReport:
    """Детектор довеском к ревью: он не имеет права уронить черновик.

    Сигналы деградируют внутри себя — недоступный приходит с пометкой, а не с
    нулём, — но неожиданный сбой остаётся возможным, и цена ему здесь потерянный
    отчёт, а не потерянное ревью. Отсюда единственный в сервисе широкий перехват:
    он ограничен необязательной половиной ответа.

    Гейт детектору больше не указ: пропуск по формальной проверке ничего не
    говорит о самостоятельности работы, а раньше непройденное дословное
    требование отменяло заодно и разбор на признаки ГенИИ.
    """
    try:
        return await run_in_threadpool(
            partial(ai.detect, bundle, texts, rubric, student_name=student_name)
        )
    except Exception as exc:
        _log.warning("детектор не отработал: %s", exc, exc_info=True)
        return DetectionReport.unavailable(f"Детектор не отработал: {exc}")


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
async def list_rubrics(request: Request, user: RequireReviewer) -> list[RubricSummary]:
    """Каталог рубрик. Добавить курс — значит положить рядом ещё один JSON."""
    store: RubricStore = request.app.state.rubrics
    return [RubricSummary.of(store.get(rubric_id)) for rubric_id in store.ids]  # type: ignore[arg-type]


@router.get("/rubrics/{assignment_id}", summary="One rubric in full")
async def get_rubric(assignment_id: str, request: Request, user: RequireReviewer) -> Rubric:
    """Критерии, якоря и шкала — то, против чего ставился каждый вердикт."""
    return _rubric(request, assignment_id, None)


@router.post("/rubrics/compile", summary="Turn an assignment condition into a rubric draft")
async def compile_rubric(
    body: CompileRubricRequest, request: Request, user: RequireMethodist
) -> CompileRubricResponse:
    """Разобрать условие задания и предложить рубрику.

    Результат — черновик, а не рубрика: он не сохраняется в каталог и не
    участвует в проверках, пока методист его не подтвердит. Это единственное
    место конвейера, где ошибка модели тиражируется на весь поток, поэтому
    человек в цикле обязателен по устройству, а не по настройке.

    Каждый критерий несёт цитату из условия, сверенную с текстом программно;
    `grounded_share` показывает, какая доля критериев подтверждена дословно.
    Всё, чего в условии нет — шкала, порог, штрафы, — не выдумывается, а
    выносится в `open_questions`.

    ``502`` — модель не ответила или вернула неразбираемое.
    """
    ai: AIService = request.app.state.ai
    compiler = RubricCompiler(ai.gateway)
    try:
        draft = await run_in_threadpool(
            partial(
                compiler.compile,
                body.condition_text,
                assignment_id=body.assignment_id,
                course=body.course,
                hint=body.hint,
            )
        )
    except CompilerError as exc:
        _log.warning("рубрика %s не собрана: %s", body.assignment_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CompileRubricResponse(draft=draft, grounded_share=draft.grounded_share)


@router.post("/rubrics", summary="Confirm a rubric and put it into the catalogue")
async def confirm_rubric(
    body: ConfirmRubricRequest, request: Request, user: RequireMethodist
) -> ConfirmRubricResponse:
    """Принять рубрику: с этого момента по ней проверяются работы потока.

    Это тот самый шаг, ради которого компилятор ничего не сохраняет сам. Здесь
    же — единственная проверка, которую нельзя доверить модели: код смотрит, что
    рубрика вообще считается. Недостижимый порог зачёта, обязательный минимум
    выше максимума критерия, повторяющиеся идентификаторы — всё это ломает
    подсчёт балла не на одной работе, а на каждой до конца курса.

    ``409`` — рубрика с таким идентификатором уже есть; перезапись только явным
    `overwrite`, потому что по старой уже могли быть выставлены баллы.
    ``422`` — рубрика не считается, в ответе список поломок.
    """
    store: RubricStore = request.app.state.rubrics
    # Метку черновика снимаем: рубрика не может одновременно ждать подтверждения
    # и быть подтверждённой.
    note = body.rubric.source_note.replace(DRAFT_NOTE, "").strip()
    stamp = f"Подтверждено: {body.confirmed_by}, {datetime.now(tz=UTC).date().isoformat()}."
    rubric = body.rubric.model_copy(
        update={"source_note": f"{note} {stamp}".strip()}
    )
    try:
        path = store.save(rubric, overwrite=body.overwrite)
    except RubricRejected as exc:
        raise HTTPException(status_code=422, detail=exc.problems) from exc
    except RubricExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"не удалось записать рубрику: {exc}") from exc

    _log.info("рубрика %s подтверждена: %s", rubric.assignment_id, body.confirmed_by)
    return ConfirmRubricResponse(rubric=rubric, path=str(path))


@router.delete("/rubrics/{assignment_id}", summary="Remove a rubric from the catalogue", status_code=204)
async def delete_rubric(assignment_id: str, request: Request, user: RequireMethodist) -> None:
    """Submissions already scored against this rubric keep meaning what they
    meant — `Submission.rubric_snapshot` froze it at scoring time — so this
    only takes it out of future `POST /review` calls.

    ``404`` — no such rubric.
    """
    store: RubricStore = request.app.state.rubrics
    try:
        store.delete(assignment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"рубрика {assignment_id!r} не найдена") from exc


async def _assignment(session: AsyncSession, assignment_id: UUID | None) -> Assignment | None:
    """Задание, если его назвали. ``404`` — назвали несуществующее."""
    if assignment_id is None:
        return None
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="задание не найдено")
    return assignment


async def _resolve_reviewer(session: AsyncSession, user: User, reviewer_username: str | None) -> User:
    """Who a persisted submission is assigned to.

    Defaults to whoever called the endpoint — running `/review` is how a
    reviewer claims a submission. Handing it to someone else on creation is
    an admin privilege, same as `POST /submissions/{id}/reassign`.
    """
    if reviewer_username is None:
        return user
    if Role(user.role) is not Role.ADMIN:
        raise HTTPException(
            status_code=403, detail="назначать сдачу другому ревьюеру может только admin"
        )
    target = (
        await session.execute(select(User).where(User.username == reviewer_username))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail=f"пользователь {reviewer_username!r} не найден")
    return target


@router.post("/review", summary="Draft a review of a submission against a rubric")
async def review(
    body: ReviewRequest, request: Request, user: RequireReviewer, session: Session
) -> ReviewResponse:
    """Собрать сдачу по ссылке и вернуть черновик ревью с проверенными цитатами.

    Балл считает код, а не модель: она отвечает по каждому критерию отдельно и
    обязана приложить цитату, которая затем сверяется с текстом файла.
    Вердикты без подтверждённой цитаты помечены `needs_human_attention`.

    Прогон сохраняется как `Submission` — карточка доступна дальше по
    `submission_id` через `GET /submissions/{id}` и попадает в очередь
    ревьюера (`GET /me/queue`). `with_detection: true` заодно прогоняет
    детектор ГенИИ на тех же `bundle`/`texts`, без второго похода к источнику
    сдачи. `reviewer_username` — только для admin, назначить сдачу не себе.

    ``403`` — `reviewer_username` указан не администратором.
    ``404`` — рубрика или `reviewer_username` не найдены.
    ``422`` — ссылка или источник неверны. ``502`` — источник сдачи не ответил.
    """
    assignment = await _assignment(session, body.assignment_id)
    if assignment is not None:
        # Срок и рубрику диктует задание, а не тело запроса. Раньше дедлайн
        # вводил ревьюер руками на каждой работе: опечатка в дате давала
        # штраф за просрочку там, где просрочки не было, и объяснить такой
        # балл студенту было нечем.
        body = body.model_copy(
            update={"rubric_id": assignment.rubric_key, "deadline_at": assignment.deadline_at}
        )
    rubric = _rubric(request, body.rubric_id, body.rubric)
    reviewer = await _resolve_reviewer(session, user, body.reviewer_username)
    bundle = await ingest_submission(request, body)

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
        student_name=body.student_name,
    )
    detection = (
        await _detection(ai, bundle, texts, rubric, draft, student_name=body.student_name)
        if body.with_detection
        else None
    )

    files = [ArtifactTextOut.of(text) for text in texts]
    submission = Submission(
        id=bundle.submission_id,
        origin_url=bundle.origin_url,
        source=bundle.source.value,
        rubric_key=rubric.assignment_id,
        rubric_snapshot=rubric.model_dump(mode="json"),
        assignment_id=assignment.id if assignment else None,
        reviewer_id=reviewer.id,
        bundle=bundle.model_dump(mode="json"),
        files=[f.model_dump(mode="json") for f in files],
        draft=draft.model_dump(mode="json"),
        detection=detection.model_dump(mode="json") if detection else None,
        condition_text=body.condition_text,
        submitted_at=bundle.submitted_at,
        deadline_at=bundle.deadline_at,
    )
    session.add(submission)
    await session.commit()

    return ReviewResponse(
        bundle=bundle, files=files, draft=draft, detection=detection, submission_id=submission.id
    )


@router.post("/detect", summary="Look for signs of generative-AI authorship")
async def detect(body: DetectRequest, request: Request, user: RequireReviewer) -> DetectResponse:
    """Ансамбль из четырёх сигналов: форензика истории, стилометрия, перплексия, judge.

    Вывод рекомендательный. Он не является доказательством, на балл не влияет
    и содержит явный список того, чего проверка не видела: недоступные сигналы
    и файлы, доступные только фрагментом.

    Разовый прогон, ничего не сохраняет: чтобы отчёт лёг в карточку сдачи и
    был виден через `GET /submissions/{id}/ai-detection`, запросите его вместе
    с ревью — `POST /review` с `with_detection: true`.
    """
    rubric = (
        _rubric(request, body.rubric_id, None) if body.rubric_id else None
    )
    bundle = await ingest_submission(request, body)

    ai: AIService = request.app.state.ai
    texts = await ai.prepare(bundle)
    report = await run_in_threadpool(
        partial(ai.detect, bundle, texts, rubric, student_name=body.student_name)
    )
    return DetectResponse(
        bundle=bundle,
        files=[ArtifactTextOut.of(text) for text in texts],
        report=report,
    )


@router.get("/cost", summary="Model spend since startup")
async def cost(request: Request, user: RequireAdmin) -> CostSummary:
    """Журнал шлюза в цифрах: сколько вызовов ушло наружу, сколько это стоило."""
    ai: AIService = request.app.state.ai
    return CostSummary.model_validate(ai.cost_summary)
