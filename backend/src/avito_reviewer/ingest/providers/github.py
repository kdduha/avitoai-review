from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import ClassVar, TypeVar

from githubkit import GitHub
from githubkit.exception import GitHubException
from githubkit_schemas.latest.models import (
    Blob,
    Commit,
    DiffEntry,
    GitTree,
    PullRequest,
    SimpleUser,
)

from avito_reviewer.config import GitHubConfig
from avito_reviewer.ingest.diff import added_line_ranges, changed_ranges_by_path
from avito_reviewer.ingest.errors import InvalidLinkError, ProviderFetchError
from avito_reviewer.ingest.models import (
    ChangeStatus,
    FileArtifact,
    HistoryEvent,
    IngestContext,
    LineRange,
    StudentRef,
    SubmissionBundle,
    SubmissionSource,
    TextSegment,
    TreeEntry,
)
from avito_reviewer.ingest.providers.base import SubmissionProvider

_T = TypeVar("_T")
_PER_PAGE = 100
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_LINK_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)
_STATUS: dict[str, ChangeStatus] = {
    "added": ChangeStatus.ADDED,
    "removed": ChangeStatus.REMOVED,
    "modified": ChangeStatus.MODIFIED,
    "renamed": ChangeStatus.RENAMED,
    "copied": ChangeStatus.MODIFIED,
    "changed": ChangeStatus.MODIFIED,
    "unchanged": ChangeStatus.UNCHANGED,
}
_LANG: dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".sh": "shell",
    ".sql": "sql",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".proto": "protobuf",
    ".ipynb": "jupyter",
}


@dataclass(slots=True)
class _Blob:
    text: str | None
    size: int
    is_binary: bool
    truncated: bool


def _stat_lines(stats: object) -> tuple[int, int]:
    added = getattr(stats, "additions", None)
    removed = getattr(stats, "deletions", None)
    return (added if isinstance(added, int) else 0, removed if isinstance(removed, int) else 0)


def _guess_lang(path: str) -> str | None:
    name = PurePosixPath(path).name.lower()
    if name in {"dockerfile", "makefile"}:
        return name
    return _LANG.get(PurePosixPath(name).suffix)


def _decode_blob(blob: Blob) -> _Blob:
    size = blob.size or 0
    if blob.encoding != "base64":
        return _Blob(text=None, size=size, is_binary=False, truncated=True)
    raw = base64.b64decode(blob.content)
    if b"\x00" in raw:
        return _Blob(text=None, size=size or len(raw), is_binary=True, truncated=False)
    return _Blob(
        text=raw.decode("utf-8", "replace"),
        size=size or len(raw),
        is_binary=False,
        truncated=False,
    )


class GitHubProvider(SubmissionProvider):
    source: ClassVar[SubmissionSource] = SubmissionSource.GITHUB_PR

    def __init__(self, config: GitHubConfig, *, author_salt: str = "") -> None:
        self._config = config
        self._salt = author_salt
        token = config.token.get_secret_value() if config.token else None
        self._gh = GitHub(token, base_url=config.base_url)

    async def aclose(self) -> None:
        await self._gh.__aexit__()

    async def fetch(self, link: str, *, context: IngestContext) -> SubmissionBundle:
        owner, repo, number = self._parse_link(link)
        try:
            pr = (await self._gh.rest.pulls.async_get(owner, repo, number)).parsed_data
            changed = await self._collect(
                lambda page: self._files_page(owner, repo, number, page), self._config.max_files
            )
            commits = await self._collect(
                lambda page: self._commits_page(owner, repo, number, page), self._config.max_commits
            )
            tree = (
                await self._gh.rest.git.async_get_tree(owner, repo, pr.head.sha, recursive="true")
            ).parsed_data
            diff_text = await self._fetch_diff(owner, repo, number)
            commits = await self._with_stats(owner, repo, commits)
            blobs = await self._load_blobs(owner, repo, self._select_paths(changed, tree))
        except GitHubException as exc:
            raise ProviderFetchError(str(exc)) from exc

        return self._to_bundle(pr, diff_text, changed, commits, tree, blobs, context)

    def _parse_link(self, link: str) -> tuple[str, str, int]:
        match = _LINK_RE.match(link.strip())
        if match is None:
            raise InvalidLinkError(f"not a github pull-request URL: {link!r}")
        return match["owner"], match["repo"].removesuffix(".git"), int(match["number"])

    async def _collect(
        self, page_fetch: Callable[[int], Awaitable[list[_T]]], limit: int
    ) -> list[_T]:
        items: list[_T] = []
        page = 1
        while len(items) < limit:
            batch = await page_fetch(page)
            items.extend(batch)
            if len(batch) < _PER_PAGE:
                break
            page += 1
        return items[:limit]

    async def _files_page(self, owner: str, repo: str, number: int, page: int) -> list[DiffEntry]:
        resp = await self._gh.rest.pulls.async_list_files(
            owner, repo, number, per_page=_PER_PAGE, page=page
        )
        return resp.parsed_data

    async def _commits_page(self, owner: str, repo: str, number: int, page: int) -> list[Commit]:
        resp = await self._gh.rest.pulls.async_list_commits(
            owner, repo, number, per_page=_PER_PAGE, page=page
        )
        return resp.parsed_data

    async def _fetch_diff(self, owner: str, repo: str, number: int) -> str:
        resp = await self._gh.arequest(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}",
            headers={"Accept": "application/vnd.github.diff"},
        )
        return resp.text

    async def _with_stats(self, owner: str, repo: str, commits: list[Commit]) -> list[Commit]:
        if not commits:
            return commits
        semaphore = asyncio.Semaphore(self._config.concurrency)

        async def one(sha: str) -> Commit:
            async with semaphore:
                return (await self._gh.rest.repos.async_get_commit(owner, repo, sha)).parsed_data

        tasks = [asyncio.create_task(one(commit.sha)) for commit in commits]
        return [await task for task in tasks]

    async def _load_blobs(
        self, owner: str, repo: str, items: list[tuple[str, str]]
    ) -> dict[str, _Blob]:
        semaphore = asyncio.Semaphore(self._config.concurrency)

        async def one(path: str, sha: str) -> tuple[str, _Blob]:
            async with semaphore:
                blob = (await self._gh.rest.git.async_get_blob(owner, repo, sha)).parsed_data
            return path, _decode_blob(blob)

        tasks = [asyncio.create_task(one(path, sha)) for path, sha in items]
        return dict([await task for task in tasks])

    def _excluded(self, path: str) -> bool:
        return any(fnmatch(path, pattern) for pattern in self._config.exclude_globs)

    def _select_paths(self, changed: list[DiffEntry], tree: GitTree) -> list[tuple[str, str]]:
        sha_by_path = {item.path: item.sha for item in tree.tree if item.type == "blob"}
        size_by_path = {
            item.path: (item.size if isinstance(item.size, int) else 0)
            for item in tree.tree
            if item.type == "blob"
        }

        picked = [
            c.filename
            for c in changed
            if c.status != "removed" and c.filename in sha_by_path
        ]

        if self._config.context_scope == "full":
            for path in sha_by_path:
                if len(picked) >= self._config.max_files:
                    break
                if path in picked or self._excluded(path):
                    continue
                if size_by_path.get(path, 0) > self._config.max_file_bytes:
                    continue
                picked.append(path)

        picked = picked[: self._config.max_files]
        return [(path, sha_by_path[path]) for path in picked]

    def _to_bundle(
        self,
        pr: PullRequest,
        diff_text: str,
        changed: list[DiffEntry],
        commits: list[Commit],
        tree: GitTree,
        blobs: dict[str, _Blob],
        context: IngestContext,
    ) -> SubmissionBundle:
        login = pr.user.login if pr.user else "unknown"
        ranges = changed_ranges_by_path(diff_text)
        meta_by_path = {entry.filename: entry for entry in changed}
        files = self._build_files(blobs, meta_by_path, ranges)

        return SubmissionBundle(
            source=self.source,
            student_ref=StudentRef(
                internal_id=context.student_internal_id or self._hash(login),
                external_handles={"github": login},
            ),
            assignment_id=context.assignment_id,
            submitted_at=pr.created_at,
            deadline_at=context.deadline_at,
            base_ref=pr.base.sha,
            head_ref=pr.head.sha,
            files=files,
            tree=[
                TreeEntry(
                    path=item.path,
                    kind="dir" if item.type == "tree" else "file",
                    size_bytes=item.size if isinstance(item.size, int) else None,
                )
                for item in tree.tree
            ],
            diff=diff_text,
            segments=[
                TextSegment(
                    segment_id=file.path,
                    artifact_path=file.path,
                    start=0,
                    end=len(file.content),
                    text=file.content,
                )
                for file in files
                if not file.is_binary and file.content
            ],
            history=self._build_history(commits),
            raw_ref=pr.html_url,
        )

    def _build_files(
        self,
        blobs: dict[str, _Blob],
        meta_by_path: dict[str, DiffEntry],
        ranges: dict[str, list[LineRange]],
    ) -> list[FileArtifact]:
        files = [
            self._artifact(path, blob, meta_by_path.get(path), ranges)
            for path, blob in blobs.items()
        ]
        files.extend(
            self._artifact(path, None, meta, ranges)
            for path, meta in meta_by_path.items()
            if path not in blobs
        )
        return files

    def _artifact(
        self,
        path: str,
        blob: _Blob | None,
        meta: DiffEntry | None,
        ranges: dict[str, list[LineRange]],
    ) -> FileArtifact:
        patch = meta.patch if meta is not None and isinstance(meta.patch, str) else None
        previous = (
            meta.previous_filename
            if meta is not None and isinstance(meta.previous_filename, str)
            else None
        )
        return FileArtifact(
            path=path,
            lang=_guess_lang(path),
            content=blob.text or "" if blob else "",
            size_bytes=blob.size if blob else 0,
            is_binary=blob.is_binary if blob else False,
            truncated=blob.truncated if blob else False,
            change_status=(
                _STATUS.get(meta.status, ChangeStatus.MODIFIED)
                if meta is not None
                else ChangeStatus.UNCHANGED
            ),
            in_diff=meta is not None,
            patch=patch,
            previous_path=previous,
            changed_ranges=ranges.get(path) or (added_line_ranges(patch) if patch else []),
        )

    def _build_history(self, commits: list[Commit]) -> list[HistoryEvent]:
        return [self._history_event(commit) for commit in commits]

    def _history_event(self, commit: Commit) -> HistoryEvent:
        git_author = commit.commit.author
        api_author = commit.author
        login = api_author.login if isinstance(api_author, SimpleUser) else None
        name = git_author.name if git_author and isinstance(git_author.name, str) else None
        when = git_author.date if git_author and isinstance(git_author.date, datetime) else _EPOCH
        added, removed = _stat_lines(commit.stats)
        message = commit.commit.message.splitlines()
        return HistoryEvent(
            ref=commit.sha,
            author_hash=self._hash(login or name or "unknown"),
            timestamp=when,
            added_lines=added,
            removed_lines=removed,
            message=message[0] if message else None,
        )

    def _hash(self, value: str) -> str:
        return hashlib.sha256(f"{self._salt}:{value}".encode()).hexdigest()[:16]
