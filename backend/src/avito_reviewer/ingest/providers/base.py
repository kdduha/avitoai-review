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

    @abstractmethod
    async def fetch(self, link: str, *, context: IngestContext) -> SubmissionBundle: ...

    async def aclose(self) -> None:
        return None
