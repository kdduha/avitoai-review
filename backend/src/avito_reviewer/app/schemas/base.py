from __future__ import annotations

from pydantic import BaseModel

from avito_reviewer.ingest import SubmissionSource


class HealthResponse(BaseModel):
    status: str


class InitResponse(BaseModel):
    service: str
    version: str
    sources: list[SubmissionSource]
    llm_provider: str
    """`fake` / `local` / `external` — куда ходит шлюз, а не чем отвечает."""
    llm_model: str = ""
    """Модель, которой отвечают. Провайдера мало: «модель: fake» в интерфейсе
    читается как имя модели, хотя это способ подключения."""
    rubrics: list[str]
    reviewers: list[str]
    demo_login: bool = False
    """Доступен ли вход одной кнопкой (`POST /auth/demo`). Экран входа рисует
    её по этому флагу: спрашивать сервер иначе неоткуда, `/init` открыт без
    токена."""
