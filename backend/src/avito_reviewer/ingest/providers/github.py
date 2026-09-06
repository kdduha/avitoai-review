from __future__ import annotations

import asyncio
import base64
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import ClassVar, TypeVar

from githubkit import GitHub
from githubkit.exception import GitHubException
from githubkit.retry import RETRY_SERVER_ERROR
from githubkit_schemas.latest.models import (
    Blob,
    Commit,
    DiffEntry,
    GitTree,
    PullRequest,
    SimpleUser,
)

from avito_reviewer.config import GitHubConfig
from avito_reviewer.ingest.classify import classify
from avito_reviewer.ingest.content import github_ref, parse_github_locator
from avito_reviewer.ingest.diff import added_line_ranges
from avito_reviewer.ingest.errors import InvalidLinkError, ProviderFetchError
from avito_reviewer.ingest.identity import author_hash
from avito_reviewer.ingest.models import (
    Artifact,
    ArtifactRole,
    ChangeStatus,
    IngestContext,
    RepoContext,
    Revision,
    StudentRef,
    SubmissionBundle,
    SubmissionSource,
)
from avito_reviewer.ingest.providers.base import SubmissionProvider

_log = logging.getLogger(__name__)
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
    "copied": ChangeStatus.ADDED,
    "changed": ChangeStatus.MODIFIED,
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
    is_binary: bool


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
    if blob.encoding != "base64":
        return _Blob(text=None, is_binary=False)
    raw = base64.b64decode(blob.content)
    if b"\x00" in raw:
        return _Blob(text=None, is_binary=True)
    return _Blob(text=raw.decode("utf-8", "replace"), is_binary=False)


def _describe(exc: GitHubException, owner: str, repo: str, number: int) -> str:
    """Человеческое объяснение отказа GitHub.

    Голый repr исключения клиента уходит прямо в ответ API, а самая частая
    причина отказа — отсутствующий или недостаточный токен. Ревьюер должен
    прочитать, что чинить, а не имя внутренней модели githubkit.
    """
    target = f"{owner}/{repo}#{number}"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 404:
        return f"{target}: PR не найден или репозиторий недоступен этому токену"
    if status in (401, 403):
        return (
            f"{target}: GitHub отказал ({status}) — проверьте INGEST_GITHUB__TOKEN "
            f"и его права"
        )
    if status == 429:
        return f"{target}: исчерпан лимит запросов GitHub, попробуйте позже"
    if status is not None:
        return f"{target}: GitHub ответил {status}"
    return f"{target}: {exc}"


class GitHubProvider(SubmissionProvider):
    source: ClassVar[SubmissionSource] = SubmissionSource.GITHUB_PR
    content_scheme: ClassVar[str] = "github"

    def __init__(self, config: GitHubConfig, *, author_salt: str = "") -> None:
        self._config = config
        self._salt = author_salt
        token = config.token.get_secret_value() if config.token else None
        # Только пятисотки. Штатная политика githubkit пережидает и лимит запросов
        # sleep-ом до часа: запрос ревьюера повис бы вместо внятной ошибки.
        self._gh = GitHub(token, base_url=config.base_url, auto_retry=RETRY_SERVER_ERROR)

    async def aclose(self) -> None:
        await self._gh.__aexit__()

    async def fetch_content(self, locator: str) -> str | None:
        """Read one blob at a fixed ref. Returns ``None`` for anything not readable as text.

        A body that cannot be read is not an error here: the review layer falls back to
        the artifact's diff and marks the file as shown in part. Upstream failures are
        logged rather than raised for the same reason -- one unreachable file must not
        cost the whole submission.
        """
        target = parse_github_locator(locator)
        if target is None:
            _log.warning("github: malformed content locator %r", locator)
            return None
        try:
            content = (
                await self._gh.rest.repos.async_get_content(
                    target.owner, target.repo, target.path, ref=target.ref
                )
            ).parsed_data
        except GitHubException as exc:
            _log.warning("github: cannot read %s: %s", locator, exc)
            return None

        if getattr(content, "type", None) != "file" or getattr(content, "encoding", "") != "base64":
            return None
        raw = base64.b64decode(getattr(content, "content", "") or "")
        return None if b"\x00" in raw else raw.decode("utf-8", "replace")

    def content_ref_for(self, root: str, ref: str, path: str) -> str | None:
        owner, _, repo = root.partition("/")
        return github_ref(owner, repo, ref, path) if owner and repo else None

    async def fetch(self, link: str, *, context: IngestContext) -> SubmissionBundle:
        owner, repo, number = self._parse_link(link)
        try:
            pr = (await self._gh.rest.pulls.async_get(owner, repo, number)).parsed_data
            changed = await self._collect(
                lambda page: self._files_page(owner, repo, number, page), self._config.max_artifacts
            )
            commits = await self._collect(
                lambda page: self._commits_page(owner, repo, number, page), self._config.max_commits
            )
            tree = (
                await self._gh.rest.git.async_get_tree(owner, repo, pr.head.sha, recursive="true")
            ).parsed_data
            commits = await self._with_stats(owner, repo, commits)
            excerpts = await self._load_excerpts(owner, repo, changed, tree)
        except GitHubException as exc:
            raise ProviderFetchError(_describe(exc, owner, repo, number)) from exc

        _log.debug(
            "github: %s/%s#%d — %d changed files, %d excerpts, %d commits",
            owner,
            repo,
            number,
            len(changed),
            len(excerpts),
            len(commits),
        )
        return self._to_bundle(owner, repo, pr, changed, commits, tree, excerpts, context)

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

    async def _with_stats(self, owner: str, repo: str, commits: list[Commit]) -> list[Commit]:
        if not commits:
            return commits
        semaphore = asyncio.Semaphore(self._config.concurrency)

        async def one(sha: str) -> Commit:
            async with semaphore:
                return (await self._gh.rest.repos.async_get_commit(owner, repo, sha)).parsed_data

        tasks = [asyncio.create_task(one(commit.sha)) for commit in commits]
        return [await task for task in tasks]

    def _tree_sizes(self, tree: GitTree) -> dict[str, int]:
        return {
            item.path: (item.size if isinstance(item.size, int) else 0)
            for item in tree.tree
            if item.type == "blob"
        }

    def _tree_shas(self, tree: GitTree) -> dict[str, str]:
        return {item.path: item.sha for item in tree.tree if item.type == "blob"}

    def _excluded(self, path: str) -> bool:
        return any(fnmatch(path, pattern) for pattern in self._config.exclude_globs)

    async def _load_excerpts(
        self, owner: str, repo: str, changed: list[DiffEntry], tree: GitTree
    ) -> dict[str, _Blob]:
        sizes = self._tree_sizes(tree)
        shas = self._tree_shas(tree)
        wanted = [
            entry.filename
            for entry in changed
            if entry.status != "removed"
            and entry.patch is not None
            and not self._excluded(entry.filename)
            and 0 < sizes.get(entry.filename, 0) <= self._config.excerpt_max_bytes
            and entry.filename in shas
        ]
        semaphore = asyncio.Semaphore(self._config.concurrency)

        async def one(path: str) -> tuple[str, _Blob]:
            async with semaphore:
                blob = (
                    await self._gh.rest.git.async_get_blob(owner, repo, shas[path])
                ).parsed_data
            return path, _decode_blob(blob)

        tasks = [asyncio.create_task(one(path)) for path in wanted]
        return dict([await task for task in tasks])

    def _to_bundle(
        self,
        owner: str,
        repo: str,
        pr: PullRequest,
        changed: list[DiffEntry],
        commits: list[Commit],
        tree: GitTree,
        excerpts: dict[str, _Blob],
        context: IngestContext,
    ) -> SubmissionBundle:
        login = pr.user.login if pr.user else "unknown"
        sizes = self._tree_sizes(tree)
        head = pr.head.sha
        artifacts = [
            self._artifact(entry, owner, repo, head, sizes, excerpts.get(entry.filename))
            for entry in changed
        ]
        return SubmissionBundle(
            source=self.source,
            origin_url=pr.html_url,
            retrieved_at=datetime.now(tz=UTC),
            student_ref=StudentRef(
                internal_id=context.student_internal_id or self._hash(login),
                external_handles={"github": login},
            ),
            submitted_at=pr.created_at,
            deadline_at=context.deadline_at,
            assignment_id=context.assignment_id,
            base_ref=pr.base.sha,
            head_ref=head,
            artifacts=artifacts,
            revisions=[self._revision(commit) for commit in commits],
            repo=self._repo_context(owner, repo, pr, tree),
        )

    def _artifact(
        self,
        entry: DiffEntry,
        owner: str,
        repo: str,
        head: str,
        sizes: dict[str, int],
        blob: _Blob | None,
    ) -> Artifact:
        path = entry.filename
        excerpt = blob.text if blob else None
        return Artifact(
            path=path,
            previous_path=(
                entry.previous_filename if isinstance(entry.previous_filename, str) else None
            ),
            status=_STATUS.get(entry.status, ChangeStatus.MODIFIED),
            role=ArtifactRole.NOISE if self._excluded(path) else classify(path),
            lang=_guess_lang(path),
            is_binary=bool(blob and blob.is_binary),
            size_bytes=sizes.get(path, 0),
            line_count=excerpt.count("\n") + 1 if excerpt else None,
            changed_ranges=added_line_ranges(entry.patch) if entry.patch else [],
            diff=entry.patch if isinstance(entry.patch, str) else None,
            excerpt=excerpt,
            content_ref=(
                github_ref(owner, repo, head, path) if entry.status != "removed" else None
            ),
        )

    def _repo_context(
        self, owner: str, repo: str, pr: PullRequest, tree: GitTree
    ) -> RepoContext:
        files = [item.path for item in tree.tree if item.type == "blob"]
        cap = self._config.max_context_files
        truncated = len(files) > cap
        if truncated:
            _log.warning(
                "github: repo map truncated for %s/%s — %d of %d files kept",
                owner,
                repo,
                cap,
                len(files),
            )
        return RepoContext(
            root=f"{owner}/{repo}",
            default_branch=pr.base.ref,
            total_files=len(files),
            files=sorted(files)[:cap],
            truncated=truncated,
        )

    def _revision(self, commit: Commit) -> Revision:
        git_author = commit.commit.author
        api_author = commit.author
        login = api_author.login if isinstance(api_author, SimpleUser) else None
        name = git_author.name if git_author and isinstance(git_author.name, str) else None
        when = git_author.date if git_author and isinstance(git_author.date, datetime) else _EPOCH
        added, removed = _stat_lines(commit.stats)
        subject = commit.commit.message.splitlines()
        return Revision(
            id=commit.sha,
            authored_at=when,
            author_hash=self._hash(login or name or "unknown"),
            summary=subject[0] if subject else None,
            added_lines=added,
            removed_lines=removed,
        )

    def _hash(self, value: str) -> str:
        return author_hash(value, salt=self._salt)
