from __future__ import annotations

from collections.abc import Iterable

from avito_reviewer.config import IngestConfig
from avito_reviewer.ingest.errors import UnknownSourceError
from avito_reviewer.ingest.models import IngestContext, SubmissionBundle, SubmissionSource
from avito_reviewer.ingest.providers import GitHubProvider, SubmissionProvider


class IngestService:
    """Fetch a submission with the provider named by its :class:`SubmissionSource`."""

    def __init__(self, providers: Iterable[SubmissionProvider]) -> None:
        self._providers = {provider.source: provider for provider in providers}

    async def ingest(
        self,
        link: str,
        source: SubmissionSource,
        *,
        context: IngestContext | None = None,
    ) -> SubmissionBundle:
        provider = self._providers.get(source)
        if provider is None:
            raise UnknownSourceError(source)
        return await provider.fetch(link, context=context or IngestContext())

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()

    async def __aenter__(self) -> IngestService:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()


def create_ingest_service(config: IngestConfig | None = None) -> IngestService:
    config = config or IngestConfig()
    return IngestService([GitHubProvider(config.github, author_salt=config.author_salt)])
