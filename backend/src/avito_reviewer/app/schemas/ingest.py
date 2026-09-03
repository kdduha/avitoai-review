from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from avito_reviewer.ingest import SubmissionSource


class IngestRequest(BaseModel):
    link: str
    source: SubmissionSource = SubmissionSource.GITHUB_PR
    assignment_id: UUID | None = None
    deadline_at: datetime | None = None
    student_internal_id: str | None = None
