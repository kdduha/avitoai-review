"""Run ingest on a real GitHub PR and print the resulting SubmissionBundle.

    uv run python scripts/ingest_pr_example.py [PR_URL]

The default PR lives in a small repo (~130 files) so RepoContext.truncated stays
False. Works without a token (anonymous GitHub API, 60 req/h); set
INGEST_GITHUB__TOKEN or GITHUB_TOKEN to raise the limit.
"""

from __future__ import annotations

import asyncio
import os
import sys

from avito_reviewer.config import GitHubConfig, IngestConfig
from avito_reviewer.ingest import IngestService, SubmissionSource
from avito_reviewer.logsetup import configure_logging

configure_logging()

DEFAULT_PR = "https://github.com/psf/requests/pull/6951"


async def main(pr_url: str) -> None:
    token = os.getenv("INGEST_GITHUB__TOKEN") or os.getenv("GITHUB_TOKEN")
    config = IngestConfig(github=GitHubConfig(token=token))
    service = IngestService(config)
    try:
        bundle = await service.ingest(pr_url, SubmissionSource.GITHUB_PR)
    finally:
        await service.aclose()
    print(bundle.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PR))
