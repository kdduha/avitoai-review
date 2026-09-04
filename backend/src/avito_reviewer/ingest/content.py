from __future__ import annotations

import re
from dataclasses import dataclass

_REF_RE = re.compile(r"^(?P<scheme>[a-z0-9_]+):(?P<locator>.+)$", re.S)
_GITHUB_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^@]+)@(?P<ref>[^:]+):(?P<path>.+)$", re.S)


@dataclass(frozen=True, slots=True)
class ContentRef:
    """A parsed ``Artifact.content_ref``: which provider holds the body, and where."""

    scheme: str
    locator: str


@dataclass(frozen=True, slots=True)
class GitHubRef:
    owner: str
    repo: str
    ref: str
    path: str


def parse_ref(content_ref: str) -> ContentRef | None:
    match = _REF_RE.match(content_ref.strip())
    if match is None:
        return None
    return ContentRef(scheme=match["scheme"], locator=match["locator"])


def parse_github_locator(locator: str) -> GitHubRef | None:
    match = _GITHUB_RE.match(locator)
    if match is None:
        return None
    return GitHubRef(owner=match["owner"], repo=match["repo"], ref=match["ref"], path=match["path"])


def github_ref(owner: str, repo: str, ref: str, path: str) -> str:
    return f"github:{owner}/{repo}@{ref}:{path}"
