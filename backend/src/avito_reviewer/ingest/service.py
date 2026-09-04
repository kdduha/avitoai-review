from __future__ import annotations

from avito_reviewer.config import IngestConfig
from avito_reviewer.ingest.content import parse_ref
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
        self._by_scheme: dict[str, SubmissionProvider] = {
            provider.content_scheme: provider for provider in self._providers.values()
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

    async def fetch_content(self, content_ref: str) -> str | None:
        """Resolve an ``Artifact.content_ref`` to the file's text at its head revision.

        This is the resolver behind the review layer's ``get_file`` tool: the bundle
        carries opaque handles, and only the provider that issued one knows how to
        read it. ``None`` means the body is not retrievable as text (binary, gone,
        too large, or the provider refused) -- callers degrade to the artifact's diff.
        """
        parsed = parse_ref(content_ref)
        if parsed is None:
            return None
        provider = self._by_scheme.get(parsed.scheme)
        if provider is None:
            return None
        return await provider.fetch_content(parsed.locator)

    def content_ref_for(self, bundle: SubmissionBundle, path: str) -> str | None:
        """Handle for any repository path at the bundle's head, touched by the change or not."""
        provider = self._providers.get(bundle.source)
        if provider is None or bundle.repo is None or bundle.repo.root is None:
            return None
        if bundle.head_ref is None:
            return None
        return provider.content_ref_for(bundle.repo.root, bundle.head_ref, path)

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()
