"""GitHubProvider против замоканного клиента `githubkit`.

Реальный HTTP уже проверен для LLM-провайдера (`test_provider_http.py`) — там
клиент рукописный, и HTTP-плоскость — наш код. Здесь клиент — зрелая типизиро-
ванная библиотека, её собственный транспорт и парсинг ответа не наша забота.
Наша ответственность начинается там, где кончается `parsed_data`: собрать
`SubmissionBundle`, отфильтровать шум, посчитать карту репозитория и хэш
автора. Поэтому подменяются методы `rest.*`, а не сокет.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from avito_reviewer.config import GitHubConfig
from avito_reviewer.ingest.errors import InvalidLinkError, ProviderFetchError
from avito_reviewer.ingest.models import ChangeStatus, IngestContext
from avito_reviewer.ingest.providers.github import GitHubProvider

NOW = datetime(2026, 2, 8, 20, 0, tzinfo=UTC)
LINK = "https://github.com/acme/courier/pull/7"


def _resp(parsed):
    return SimpleNamespace(parsed_data=parsed)


def _pr(**over):
    base = dict(
        html_url=LINK,
        created_at=NOW,
        user=SimpleNamespace(login="octocat"),
        head=SimpleNamespace(sha="h" * 40),
        base=SimpleNamespace(sha="b" * 40, ref="main"),
    )
    base.update(over)
    return SimpleNamespace(**base)


def _file(filename, *, patch="@@ -0,0 +1,1 @@\n+x\n", status="added", previous=None):
    return SimpleNamespace(filename=filename, patch=patch, status=status, previous_filename=previous)


def _commit(sha, *, login="octocat", name="Author Name", when=NOW,
            message="feat: сделал", additions=10, removed=0):
    return SimpleNamespace(
        sha=sha,
        commit=SimpleNamespace(author=SimpleNamespace(name=name, date=when), message=message),
        author=SimpleNamespace(login=login),
        stats=SimpleNamespace(additions=additions, deletions=removed),
    )


def _tree(entries: dict[str, int]):
    return SimpleNamespace(
        tree=[SimpleNamespace(path=p, type="blob", size=s, sha=f"sha-{p}") for p, s in entries.items()]
    )


def _blob(text: str | None, *, binary: bool = False, encoding: str = "base64"):
    raw = b"\x00binary" if binary else (text or "").encode()
    return SimpleNamespace(encoding=encoding, content=base64.b64encode(raw).decode())


@pytest.fixture
def provider():
    return GitHubProvider(GitHubConfig())


def _wire(
    prov: GitHubProvider,
    *,
    pr,
    files,
    commits,
    tree,
    blobs: dict[str, object] | None = None,
    commit_stats: dict[str, object] | None = None,
):
    """Route every `rest.*` call the provider makes onto fixed fixtures.

    `files`/`commits` may be a single page (list) or a list of pages (for
    pagination tests) -- the fake paginates the same way GitHub does: stop
    once a page comes back shorter than `per_page`.
    """
    gh = prov._gh
    pages_files = files if files and isinstance(files[0], list) else [files]
    pages_commits = commits if commits and isinstance(commits[0], list) else [commits]

    async def list_files(owner, repo, number, *, per_page, page):
        return _resp(pages_files[page - 1] if page <= len(pages_files) else [])

    async def list_commits(owner, repo, number, *, per_page, page):
        return _resp(pages_commits[page - 1] if page <= len(pages_commits) else [])

    async def get_commit(owner, repo, sha):
        return _resp((commit_stats or {}).get(sha) or _commit(sha))

    async def get_blob(owner, repo, sha):
        path = sha.removeprefix("sha-")
        return _resp((blobs or {})[path])

    gh.rest.pulls.async_get = AsyncMock(return_value=_resp(pr))
    gh.rest.pulls.async_list_files = list_files
    gh.rest.pulls.async_list_commits = list_commits
    gh.rest.git.async_get_tree = AsyncMock(return_value=_resp(tree))
    gh.rest.repos.async_get_commit = get_commit
    gh.rest.git.async_get_blob = get_blob


def _fetch(provider, link=LINK):
    return asyncio.run(provider.fetch(link, context=IngestContext()))


# --------------------------------------------------------------------------- #
# ссылка
# --------------------------------------------------------------------------- #

def test_invalid_link_is_rejected_before_any_network_call(provider):
    with pytest.raises(InvalidLinkError):
        _fetch(provider, "https://github.com/acme/courier/issues/7")


# --------------------------------------------------------------------------- #
# сборка бандла
# --------------------------------------------------------------------------- #

def test_fetch_builds_a_bundle_from_the_response(provider):
    _wire(
        provider,
        pr=_pr(),
        files=[_file("cmd/main.go")],
        commits=[_commit("c1")],
        commit_stats={"c1": _commit("c1", additions=12)},
        tree=_tree({"cmd/main.go": 40, "go.mod": 10}),
        blobs={"cmd/main.go": _blob("package main\n")},
    )
    bundle = _fetch(provider)

    assert bundle.origin_url == LINK
    assert bundle.student_ref.external_handles == {"github": "octocat"}
    assert bundle.head_ref == "h" * 40 and bundle.base_ref == "b" * 40
    assert bundle.repo.root == "acme/courier"
    assert bundle.artifacts[0].excerpt == "package main\n"
    assert bundle.revisions[0].added_lines == 12


def test_removed_file_has_no_content_ref_and_no_excerpt(provider):
    _wire(
        provider,
        pr=_pr(),
        files=[_file("old.go", status="removed", patch=None)],
        commits=[],
        tree=_tree({}),
        blobs={},
    )
    bundle = _fetch(provider)

    artifact = bundle.artifacts[0]
    assert artifact.status is ChangeStatus.REMOVED
    assert artifact.content_ref is None
    assert artifact.diff is None


def test_renamed_file_keeps_its_previous_path(provider):
    _wire(
        provider,
        pr=_pr(),
        files=[_file("internal/new.go", status="renamed", previous="internal/old.go")],
        commits=[],
        tree=_tree({"internal/new.go": 20}),
        blobs={"internal/new.go": _blob("package internal\n")},
    )
    bundle = _fetch(provider)

    artifact = bundle.artifacts[0]
    assert artifact.status is ChangeStatus.RENAMED
    assert artifact.previous_path == "internal/old.go"


# --------------------------------------------------------------------------- #
# денилист и бюджет excerpt
# --------------------------------------------------------------------------- #

def test_excluded_paths_are_marked_noise_without_fetching_a_body(provider):
    """`*.lock` не должен стоить ни одного похода за блобом."""
    _wire(
        provider,
        pr=_pr(),
        files=[_file("pkg.lock")],
        commits=[],
        tree=_tree({"pkg.lock": 5}),
        blobs={},  # запрос за телом pkg.lock обвалил бы тест KeyError'ом
    )
    bundle = _fetch(provider)

    artifact = bundle.artifacts[0]
    assert artifact.role.value == "noise"
    assert artifact.excerpt is None


def test_files_over_the_excerpt_budget_travel_diff_only():
    config = GitHubConfig(excerpt_max_bytes=10)
    prov = GitHubProvider(config)
    _wire(
        prov,
        pr=_pr(),
        files=[_file("big.go")],
        commits=[],
        tree=_tree({"big.go": 999}),  # выше бюджета excerpt_max_bytes
        blobs={},
    )
    bundle = _fetch(prov)

    artifact = bundle.artifacts[0]
    assert artifact.excerpt is None
    assert artifact.diff is not None


def test_binary_blobs_are_flagged_and_carry_no_excerpt(provider):
    _wire(
        provider,
        pr=_pr(),
        files=[_file("asset.bin")],
        commits=[],
        tree=_tree({"asset.bin": 30}),
        blobs={"asset.bin": _blob(None, binary=True)},
    )
    bundle = _fetch(provider)

    artifact = bundle.artifacts[0]
    assert artifact.is_binary is True
    assert artifact.excerpt is None


# --------------------------------------------------------------------------- #
# пагинация и карта репозитория
# --------------------------------------------------------------------------- #

def test_commits_are_collected_across_pages():
    config = GitHubConfig(max_commits=150)
    prov = GitHubProvider(config)
    page1 = [_commit(f"c{i}") for i in range(100)]
    page2 = [_commit(f"c{i}") for i in range(100, 105)]
    _wire(prov, pr=_pr(), files=[], commits=[page1, page2], tree=_tree({}), blobs={})

    bundle = _fetch(prov)
    assert len(bundle.revisions) == 105


def test_repo_map_is_truncated_past_the_cap():
    config = GitHubConfig(max_context_files=2)
    prov = GitHubProvider(config)
    _wire(
        prov, pr=_pr(), files=[], commits=[],
        tree=_tree({"a.go": 1, "b.go": 1, "c.go": 1}), blobs={},
    )
    bundle = _fetch(prov)

    assert bundle.repo.truncated is True
    assert bundle.repo.total_files == 3
    assert len(bundle.repo.files) == 2


# --------------------------------------------------------------------------- #
# автор
# --------------------------------------------------------------------------- #

def test_author_hash_is_stable_and_salt_dependent():
    tree = _tree({})

    def bundle_for(salt: str):
        prov = GitHubProvider(GitHubConfig(), author_salt=salt)
        _wire(prov, pr=_pr(), files=[], commits=[_commit("c1", login="octocat")], tree=tree, blobs={})
        return _fetch(prov)

    same_salt_a = bundle_for("course-2026")
    same_salt_b = bundle_for("course-2026")
    other_salt = bundle_for("course-2027")

    assert same_salt_a.revisions[0].author_hash == same_salt_b.revisions[0].author_hash
    assert same_salt_a.revisions[0].author_hash != other_salt.revisions[0].author_hash


# --------------------------------------------------------------------------- #
# отказ источника
# --------------------------------------------------------------------------- #

def test_upstream_failure_becomes_a_provider_fetch_error(provider):
    from githubkit.exception import GitHubException

    class _NotFound(GitHubException):
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=404)

    provider._gh.rest.pulls.async_get = AsyncMock(side_effect=_NotFound())
    with pytest.raises(ProviderFetchError, match="PR не найден"):
        _fetch(provider)


# --------------------------------------------------------------------------- #
# дозагрузка тела файла
# --------------------------------------------------------------------------- #

def test_fetch_content_reads_a_blob_at_a_fixed_ref(provider):
    provider._gh.rest.repos.async_get_content = AsyncMock(
        return_value=_resp(SimpleNamespace(type="file", encoding="base64",
                                            content=base64.b64encode(b"hello").decode()))
    )
    text = asyncio.run(provider.fetch_content("acme/courier@" + "h" * 40 + ":a.go"))
    assert text == "hello"


def test_fetch_content_is_none_for_unreadable_targets(provider):
    from githubkit.exception import GitHubException

    provider._gh.rest.repos.async_get_content = AsyncMock(side_effect=GitHubException())
    assert asyncio.run(provider.fetch_content("acme/courier@" + "h" * 40 + ":a.go")) is None
    assert asyncio.run(provider.fetch_content("не ссылка")) is None
