from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from avito_reviewer.ai.detection import DetectionReport
from avito_reviewer.ai.review import ReviewDraft
from avito_reviewer.ai.rubric import Rubric
from avito_reviewer.db import SubmissionStatus
from avito_reviewer.ingest import SubmissionBundle

from .review import ArtifactTextOut


class SubmissionSummary(BaseModel):
    """One row of a queue: enough to triage without opening the submission."""

    id: UUID
    origin_url: str
    assignment_id: str
    status: SubmissionStatus
    reviewer_username: str | None
    score: float
    max_score: float
    passed: bool | None = None
    """`None` — порога зачёта в рубрике нет."""
    needs_human_attention: bool
    submitted_at: datetime | None
    deadline_at: datetime | None
    created_at: datetime


class SubmissionDetail(BaseModel):
    """Full card: the same shapes `/review` and `/detect` return, plus workflow state."""

    id: UUID
    status: SubmissionStatus
    reviewer_username: str | None
    approved_by_username: str | None
    approved_at: datetime | None
    bundle: SubmissionBundle
    files: list[ArtifactTextOut]
    draft: ReviewDraft
    detection: DetectionReport | None
    created_at: datetime
    updated_at: datetime
    rubric: Rubric
    """The rubric snapshot taken at review time (`Submission.rubric_snapshot`),
    not a fresh catalogue lookup — a client rendering this card (criterion
    title, max score, weight, checks) must score against what the model
    actually saw, not whatever the catalogue file says today."""


class CriterionPatch(BaseModel):
    """One criterion's manual override. Omitted fields keep the model's value."""

    criterion_id: str
    score: float | None = None
    verdict: str | None = None
    student_feedback: str | None = None


class ReviewPatchRequest(BaseModel):
    patches: list[CriterionPatch] = Field(min_length=1)


class ReassignRequest(BaseModel):
    reviewer_username: str


class DetectionVerdictRequest(BaseModel):
    verdict: Literal["confirmed", "rejected"]


class RerunResponse(BaseModel):
    submission_id: UUID
    status: SubmissionStatus


class AuditRecordOut(BaseModel):
    request_id: str
    provider: str
    model: str
    task: str
    data_class: str
    route: str
    redactions: int
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_rub: float
    error: str | None
    at: str
