from __future__ import annotations

from avito_reviewer.ingest.models import SubmissionSource


class IngestError(Exception):
    """Base class for every ingestion failure."""


class UnknownSourceError(IngestError):
    def __init__(self, source: SubmissionSource | str) -> None:
        super().__init__(f"no provider registered for source: {source!r}")
        self.source = source


class InvalidLinkError(IngestError):
    """The link is malformed for the selected provider."""


class ProviderFetchError(IngestError):
    """A provider failed to fetch submission data from its upstream."""
