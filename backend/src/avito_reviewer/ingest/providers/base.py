from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from avito_reviewer.ingest.models import IngestContext, SubmissionBundle, SubmissionSource


class SubmissionProvider(ABC):
    """Fetches a submission from one source and normalizes it to a bundle.

    The caller selects the provider explicitly by :class:`SubmissionSource`; a
    provider never inspects the link to decide whether it applies.
    """

    source: ClassVar[SubmissionSource]
    content_scheme: ClassVar[str]
    """Prefix of the ``Artifact.content_ref`` handles this provider issues and resolves."""

    @abstractmethod
    async def fetch(self, link: str, *, context: IngestContext) -> SubmissionBundle: ...

    async def fetch_content(self, locator: str) -> str | None:
        """Return the text behind a ``content_ref`` locator, or ``None`` if unavailable.

        ``locator`` is the part of ``Artifact.content_ref`` after the scheme prefix;
        only the issuing provider knows how to read it. Binary and oversized bodies
        come back as ``None`` rather than as an error: a missing body is a normal
        outcome the review layer already handles.
        """
        return None

    def content_ref_for(self, root: str, ref: str, path: str) -> str | None:
        """Build a ``content_ref`` for an arbitrary repository path at ``ref``.

        Lets the review layer reach files listed in ``RepoContext`` that the change
        itself never touched.
        """
        return None
