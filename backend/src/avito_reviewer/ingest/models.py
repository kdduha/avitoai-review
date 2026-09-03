from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SubmissionSource(StrEnum):
    GITHUB_PR = "github_pr"
    GITLAB_MR = "gitlab_mr"
    GOOGLE_DOC = "google_doc"


class ChangeStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"
    UNCHANGED = "unchanged"


class IngestContext(BaseModel):
    """Assignment-level metadata a provider cannot derive from the link alone."""

    assignment_id: UUID | None = None
    deadline_at: datetime | None = None
    student_internal_id: str | None = None


class StudentRef(BaseModel):
    internal_id: str
    external_handles: dict[str, str] = Field(default_factory=dict)


class LineRange(BaseModel):
    start: int
    end: int


class TreeEntry(BaseModel):
    path: str
    kind: Literal["file", "dir"]
    size_bytes: int | None = None


class FileArtifact(BaseModel):
    path: str
    lang: str | None = None
    content: str
    size_bytes: int
    is_binary: bool = False
    truncated: bool = False
    change_status: ChangeStatus = ChangeStatus.UNCHANGED
    in_diff: bool = False
    patch: str | None = None
    previous_path: str | None = None
    changed_ranges: list[LineRange] = Field(default_factory=list)


class TextSegment(BaseModel):
    """Normalized text of one artifact with absolute offsets for citations."""

    segment_id: str
    artifact_path: str
    start: int
    end: int
    text: str


class HistoryEvent(BaseModel):
    kind: Literal["commit", "revision"] = "commit"
    ref: str
    author_hash: str
    timestamp: datetime
    added_lines: int = 0
    removed_lines: int = 0
    message: str | None = None


class SubmissionBundle(BaseModel):
    """Canonical, source-agnostic representation of one submission."""

    submission_id: UUID = Field(default_factory=uuid4)
    source: SubmissionSource
    student_ref: StudentRef
    assignment_id: UUID | None = None
    submitted_at: datetime
    deadline_at: datetime | None = None

    base_ref: str | None = None
    head_ref: str | None = None

    files: list[FileArtifact] = Field(default_factory=list)
    tree: list[TreeEntry] = Field(default_factory=list)
    diff: str | None = None
    segments: list[TextSegment] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    raw_ref: str | None = None
