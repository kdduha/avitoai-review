from __future__ import annotations

from typing import Literal

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
    context_scope: Literal["changed", "full"] = "changed"
    max_files: int = 300
    max_file_bytes: int = 1_000_000
    max_commits: int = 200
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
