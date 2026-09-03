from __future__ import annotations

from avito_reviewer.config import IngestConfig
from avito_reviewer.ingest.errors import UnknownSourceError
from avito_reviewer.ingest.models import IngestContext, SubmissionBundle, SubmissionSource
from avito_reviewer.ingest.providers import GitHubProvider, SubmissionProvider


class IngestService:
    """Fetch a submission with the provider named by its :class:`SubmissionSource`.

    Build it directly from a config; the caller owns config loading and lifecycle
    (call :meth:`aclose` on shutdown).
    """

    def __init__(self, config: IngestConfig) -> None:
        self._providers: dict[SubmissionSource, SubmissionProvider] = {
            SubmissionSource.GITHUB_PR: GitHubProvider(
                config.github, author_salt=config.author_salt
            ),
        }

    @property
    def sources(self) -> list[SubmissionSource]:
        return list(self._providers)

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
