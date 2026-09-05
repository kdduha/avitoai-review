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
    rubrics: list[str]
    reviewers: list[str]
