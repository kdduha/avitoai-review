from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, NonNegativeInt

from avito_reviewer.app.schemas.review import SubmissionRequest
from avito_reviewer.distribution import (
    DistributionItem,
    Reviewer,
    Weights,
    WorkProfile,
)


class WorkProfileRequest(SubmissionRequest):
    """Ссылка на сдачу, из которой нужно собрать профиль работы."""

    rubric_id: str | None = Field(
        default=None,
        description=(
            "Идентификаторы критериев, чтобы `risk_criteria` ссылались на "
            "настоящую рубрику, а не на выдуманные номера"
        ),
    )
    condition_text: str = ""


class WorkProfileResponse(BaseModel):
    """Профиль и готовая к распределению работа.

    `item` отдаётся собранным намеренно: `author_hashes` — внутреннее правило
    псевдонимизации, и просить клиента его воспроизвести значило бы раздать
    наружу то, что должно жить в одном месте.
    """

    profile: WorkProfile
    item: DistributionItem


class DistributeRequest(BaseModel):
    """Что распределяем, между кем и с какой текущей загрузкой."""

    items: list[DistributionItem] = Field(min_length=1)
    reviewers: list[Reviewer] | None = Field(
        default=None, description="Пул вместо каталога. Пусто — берётся каталог"
    )
    reviewer_ids: list[str] = Field(
        default_factory=list, description="Подмножество каталога. Пусто — весь каталог"
    )
    committed_minutes: dict[str, NonNegativeInt] = Field(
        default_factory=dict,
        description=(
            "Занятые минуты по ревьюерам на момент запроса. Только отсюда: "
            "загрузка меняется каждый час, и в карточке ей не место"
        ),
    )
    now: datetime | None = Field(
        default=None, description="Отсчёт для риска не успеть к сроку"
    )
    weights: Weights | None = None
    max_items_per_reviewer: int | None = None
