from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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
