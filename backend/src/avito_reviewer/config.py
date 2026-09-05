from __future__ import annotations

import json

from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/*",
    "*/__pycache__/*",
    "*/.venv/*",
    "*/node_modules/*",
    "*/mlruns/*",
    "*.lock",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.pdf",
    "*.zip",
)


class GitHubConfig(BaseModel):
    token: SecretStr | None = None
    base_url: str | None = None

    # Inline an artifact's full text only when it fits this budget; larger files
    # travel as diff-only and are fetched on demand via Artifact.content_ref.
    excerpt_max_bytes: int = 16_000
    # Hard caps so a huge PR / repo cannot blow up the bundle.
    max_artifacts: int = 300
    max_context_files: int = 500
    max_commits: int = 100
    concurrency: int = 8
    exclude_globs: tuple[str, ...] = _DEFAULT_EXCLUDES


class IngestConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INGEST_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    author_salt: str = ""
    github: GitHubConfig = Field(default_factory=GitHubConfig)


class LLMConfig(BaseModel):
    """Where model calls go. One OpenAI-compatible client serves both routes.

    Switching the whole contour to local models is a single environment variable
    (``AI_LLM__PROVIDER=local``), which is what makes the private-perimeter claim
    demonstrable rather than aspirational.
    """

    provider: Literal["fake", "local", "external"] = "fake"

    # Любой OpenAI-совместимый эндпоинт: aitunnel, OpenRouter, прокси команды.
    # Меняются только эти три поля, клиент один и тот же.
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.aitunnel.ru/v1"
    api_key: SecretStr | None = None

    local_model: str = "qwen2.5-7b-instruct"
    local_base_url: str = "http://localhost:11434/v1"

    task_models: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)
    """Модель на задачу: `{"compile": "gpt-5.6-luna-pro"}`.

    Матрица роутинга из архитектуры §8.3. Массовые задачи идут на дешёвой
    модели, а те, чей текст читает человек и чья ошибка тиражируется, — на
    сильной. Rubric Compiler считается один раз на задание, и цена там роли
    не играет, зато нестабильность стоит дорого.
    """

    @field_validator("task_models", mode="before")
    @classmethod
    def _parse_matrix(cls, value: object) -> object:
        """Разобрать матрицу самостоятельно, чтобы пустое значение не роняло старт.

        `docker compose` подставляет `${AI_LLM__TASK_MODELS:-}` пустой строкой,
        когда переменной нет. Штатный разбор pydantic-settings пробует прочесть
        её как JSON ещё до валидаторов и падает так, что в сообщении не видно
        ни поля, ни причины, — а приложение при этом не поднимается вовсе.
        """
        if not isinstance(value, str):
            return value
        if not value.strip():
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AI_LLM__TASK_MODELS должен быть JSON-объектом "
                f'вида {{"compile": "модель"}}: {exc}'
            ) from exc

    # Kill switch for external providers: every task is served locally or fails.
    force_local: bool = False
    timeout: int = 120
    max_retries: int = 2

    @field_validator("provider", mode="before")
    @classmethod
    def _accept_legacy_names(cls, value: object) -> object:
        """`openrouter` из старых конфигов означает то же, что `external`."""
        return "external" if value == "openrouter" else value


class ContentConfig(BaseModel):
    """Budget for pulling artifact bodies the bundle did not inline.

    Ingest inlines a file only within its excerpt budget; everything larger arrives
    diff-only. These caps decide how much of that is worth fetching before a run.
    """

    max_files: int = 24
    max_file_bytes: int = 400_000


class ReviewOptions(BaseModel):
    batch_size: int = 3
    temperature: float = 0.0
    max_tokens: int = 6000
    """Бюджет на ответ. У рассуждающих моделей `reasoning` тратит его же, и на
    трёх критериях 3000 не хватало: JSON обрывался на середине."""
    skip_auto_verifiable: bool = False


class DetectionOptions(BaseModel):
    weight_forensics: float = 0.35
    weight_perplexity: float = 0.25
    weight_stylometry: float = 0.15
    weight_judge: float = 0.25
    use_judge: bool = True


class DistributionOptions(BaseModel):
    max_items_per_reviewer: int = 0
    """0 — предела по числу работ нет, ограничивает только ёмкость в минутах."""
    max_review_minutes: int = 480
    """Потолок оценки трудоёмкости. Модель, ошибившаяся на порядок, иначе
    молча съедает капасити всего потока."""
    alternatives: int = 2
    """Сколько запасных ревьюеров показать рядом с назначением."""


class AIConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    review: ReviewOptions = Field(default_factory=ReviewOptions)
    detection: DetectionOptions = Field(default_factory=DetectionOptions)
    distribution: DistributionOptions = Field(default_factory=DistributionOptions)

    rubrics_dir: str = "rubrics"
    reviewers_dir: str = "reviewers"


class DatabaseConfig(BaseSettings):
    """Where persisted submissions, review revisions and users live.

    SQLite (via `sqlite+aiosqlite:///path`) works with the same engine for
    hermetic tests; the docker-compose service and any real deployment point
    this at Postgres.
    """

    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    dsn: str = "postgresql+asyncpg://avito:avito@localhost:5432/avito_reviewer"
    echo: bool = False


class QueueConfig(BaseSettings):
    """Redis, for the one thing actually queued today: `POST .../review/rerun`.

    Everything else on the request path stays synchronous — a rubric-sized
    LLM run is seconds, not minutes, and queuing it would only add latency.
    Rerun is different: it is explicitly fire-and-forget in the architecture
    (`POST /submissions/{id}/review/rerun`), so it is the one place arq earns
    its keep instead of sitting unused in docker-compose.
    """

    model_config = SettingsConfigDict(env_prefix="QUEUE_", env_file=".env", extra="ignore")

    redis_dsn: str = "redis://localhost:6379/0"


class AuthConfig(BaseSettings):
    """JWT auth for the hackathon-variant RBAC: one hardcoded login per role.

    Three accounts are seeded at startup — `student`, `reviewer`, `admin` —
    all sharing `seed_password`. This is exactly the reduction the
    architecture doc calls out for the hackathon timeline (§15,
    "аутентификация — один хардкод-логин на роль"); a real deployment
    replaces the seed with actual user records and overrides `jwt_secret`.
    The doc's `coordinator` role (runs the stream day-to-day: reassign,
    rubrics, cost) is folded into `admin` here — one project, one methodist,
    no separate coordinator headcount to give its own account to yet.
    """

    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    jwt_secret: SecretStr = SecretStr("dev-only-change-me-in-production-please")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 480
    seed_password: str = "avito2026"


class AppConfig(BaseSettings):
    """Single construction point for every settings object the app needs.

    Each field is still its own `BaseSettings` with its own env prefix
    (`INGEST_`, `AI_`, `DB_`, `AUTH_`, `QUEUE_`) — nesting them here does not
    change how they read the environment, it just gives `main.py`, `queue.py`
    and tests one object to build instead of five. Splitting them was never
    about isolation (they all read the same process environment); it is
    about naming — `config.ai.llm.provider` reads better than a flat config
    with `ai_llm_provider` fighting `db_dsn` for the same namespace.
    """

    model_config = SettingsConfigDict(extra="ignore")

    ingest: IngestConfig = Field(default_factory=IngestConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
