from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="Реплика ревьюера")


class ProposedPatchOut(BaseModel):
    criterion_id: str
    score: float | None = None
    verdict: str | None = None
    student_feedback: str | None = None


class ChatMessageOut(BaseModel):
    """Один сохранённый шаг транскрипта — то, что отдаёт `GET .../chat`."""

    id: UUID
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    proposed_patch: ProposedPatchOut | None = None
    created_at: datetime
