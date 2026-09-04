from typing import TYPE_CHECKING, Any

from avito_reviewer.config import GitHubConfig, IngestConfig
from avito_reviewer.ingest.errors import (
    IngestError,
    InvalidLinkError,
    ProviderFetchError,
    UnknownSourceError,
)
from avito_reviewer.ingest.models import (
    Artifact,
    ArtifactRole,
    ChangeStatus,
    IngestContext,
    LineRange,
    RepoContext,
    Revision,
    StudentRef,
    SubmissionBundle,
    SubmissionSource,
)

if TYPE_CHECKING:
    from avito_reviewer.ingest.service import IngestService

__all__ = [
    "Artifact",
    "ArtifactRole",
    "ChangeStatus",
    "GitHubConfig",
    "IngestConfig",
    "IngestContext",
    "IngestError",
    "IngestService",
    "InvalidLinkError",
    "LineRange",
    "ProviderFetchError",
    "RepoContext",
    "Revision",
    "StudentRef",
    "SubmissionBundle",
    "SubmissionSource",
    "UnknownSourceError",
]


def __getattr__(name: str) -> Any:
    """Keep the provider stack (and its HTTP client) out of import paths that only need models.

    ``IngestService`` pulls in ``githubkit``; the review and detection layers import
    this package for :class:`SubmissionBundle` alone and should not pay for it.
    """
    if name == "IngestService":
        from avito_reviewer.ingest.service import IngestService

        return IngestService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
