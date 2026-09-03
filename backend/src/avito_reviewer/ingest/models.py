from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SubmissionSource(StrEnum):
    """The input provider a submission was fetched from. One value per provider."""

    GITHUB_PR = "github_pr"


class ChangeStatus(StrEnum):
    """What happened to an artifact between ``base_ref`` and ``head_ref``."""

    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


class ArtifactRole(StrEnum):
    """Coarse purpose of an artifact so the review agent can skip what it need not read.

    Assigned heuristically by ingest; a later classifier pass may refine it.
    """

    SOLUTION = "solution"  # the student's own work — the thing to grade
    EVIDENCE = "evidence"  # screenshots, plots, logs that show the work runs
    TOOLING = "tooling"    # configs, CI, generated stubs — rarely graded directly
    NOISE = "noise"        # lockfiles, build output, vendored deps — safe to ignore


class StudentRef(BaseModel):
    """Pseudonymous author identity. Holds no real name and is safe to send to an LLM."""

    internal_id: str                                                # stable per-student hash
    external_handles: dict[str, str] = Field(default_factory=dict)  # e.g. {"github": "octocat"}


class LineRange(BaseModel):
    """Inclusive, 1-based line span on the head version of an artifact."""

    start: int
    end: int


class Revision(BaseModel):
    """One entry of the submission's revision history (a commit). Feeds AI-detection forensics."""

    id: str                       # commit sha
    authored_at: datetime
    author_hash: str              # pseudonymised; == StudentRef.internal_id when self-authored
    summary: str | None = None    # commit subject line
    added_lines: int = 0
    removed_lines: int = 0


class Artifact(BaseModel):
    """One reviewable unit of the submission: a source file, a notebook, a document.

    Deliberately token-cheap: ``diff`` carries the change, ``excerpt`` carries the
    whole text only when it is small, and larger bodies are left out and fetched
    later through ``content_ref`` (see the field note).
    """

    path: str                         # provider-relative path, or document title
    previous_path: str | None = None  # set only when ``status`` is ``renamed``
    status: ChangeStatus
    role: ArtifactRole = ArtifactRole.SOLUTION
    lang: str | None = None           # language / format id, e.g. "python", "markdown"
    is_binary: bool = False           # binary artifacts carry no ``diff`` and no ``excerpt``

    size_bytes: int = 0               # size of the full head version
    line_count: int | None = None     # lines in the full head version, when known

    changed_ranges: list[LineRange] = Field(default_factory=list)  # added / modified head lines
    diff: str | None = None           # unified-diff hunks for THIS artifact only
    excerpt: str | None = None        # full head text, inlined only within the excerpt budget

    # Opaque handle to the full head text of this artifact -- NOT a URL, not meant to
    # be parsed by whoever reads the bundle. The review layer runs the LLM as an
    # agent with tools (architecture s6.3); when the model asks for a body it does
    # not hold, its `get_file(path)` tool passes this handle to a resolver that knows
    # the provider scheme and returns the bytes. GitHub emits
    # "github:<owner>/<repo>@<head_sha>:<path>". None when there is nothing to fetch
    # (a removed file). The resolver / tool is not built yet -- this is the contract
    # it will implement.
    content_ref: str | None = None


class RepoContext(BaseModel):
    """Compact map of the surrounding codebase. ``None`` for non-repository sources.

    This is only an inventory of what exists, not the code itself. Any path here (or,
    when ``truncated``, any path at all) is fetched the same way as an artifact body:
    the review layer's ``get_file(path)`` tool resolves it against ``root`` and the
    bundle's ``head_ref``.
    """

    root: str | None = None           # repository id, e.g. "owner/repo"
    default_branch: str | None = None
    total_files: int = 0              # file count at head, before capping
    files: list[str] = Field(default_factory=list)  # head file paths, no metadata; may be capped
    # True => ``files`` is only the first ``max_context_files`` paths (sorted) and the
    # repo has more; a path absent from ``files`` may still exist and be fetchable.
    truncated: bool = False


class IngestContext(BaseModel):
    """Assignment-level metadata a provider cannot derive from the link alone."""

    assignment_id: UUID | None = None
    deadline_at: datetime | None = None
    student_internal_id: str | None = None


class SubmissionBundle(BaseModel):
    """Canonical, provider-agnostic snapshot of one submission, sized to hand to an LLM.

    Every stage after ingest (Format Gate, Assignment, Review Agent, AI-Detection)
    reads only this object. It carries the change under review plus just enough
    context to reason about it. Full file bodies are intentionally NOT here: the
    review layer exposes a ``get_file`` tool to the agent that resolves an
    ``Artifact.content_ref`` (or any repo path via ``head_ref``) on demand.
    """

    submission_id: UUID = Field(default_factory=uuid4)
    source: SubmissionSource
    origin_url: str                   # human-facing link to the submission (the PR page)
    retrieved_at: datetime            # when ingest fetched the submission

    student_ref: StudentRef
    submitted_at: datetime            # when the student submitted (the PR was opened)
    deadline_at: datetime | None = None
    assignment_id: UUID | None = None

    base_ref: str | None = None       # provider-defined start of the change (git: base sha)
    head_ref: str | None = None       # provider-defined end of the change (git: head sha)

    artifacts: list[Artifact] = Field(default_factory=list)  # only units touched by the change
    revisions: list[Revision] = Field(default_factory=list)  # chronological, oldest first
    repo: RepoContext | None = None
