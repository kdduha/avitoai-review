"""Резолвер `content_ref` — контракт, который ingest оставлял незакрытым.

Ссылка на тело файла намеренно непрозрачна: кто её выдал, тот и умеет её
читать. Смысл этих тестов — в том, что разбор схемы не утекает в AI-слой.
"""

from __future__ import annotations

import asyncio

import pytest
from factories import GO_MAIN, go_bundle

from avito_reviewer.config import IngestConfig
from avito_reviewer.ingest import IngestService
from avito_reviewer.ingest.content import github_ref, parse_github_locator, parse_ref
from avito_reviewer.ingest.diff import added_line_ranges, head_lines_from_patch


def test_ref_round_trips():
    ref = github_ref("acme", "courier", "abc123", "internal/store/pg.go")
    parsed = parse_ref(ref)
    assert parsed is not None and parsed.scheme == "github"

    target = parse_github_locator(parsed.locator)
    assert target is not None
    assert (target.owner, target.repo, target.ref, target.path) == (
        "acme", "courier", "abc123", "internal/store/pg.go"
    )


def test_paths_with_separators_survive():
    parsed = parse_ref(github_ref("a", "b", "sha", "a/b/c@d:e.go"))
    assert parsed is not None
    target = parse_github_locator(parsed.locator)
    assert target is not None and target.path == "a/b/c@d:e.go"


@pytest.mark.parametrize("bad", ["", "нет схемы", "github:мусор"])
def test_malformed_refs_do_not_raise(bad):
    parsed = parse_ref(bad)
    assert parsed is None or parse_github_locator(parsed.locator) is None


def test_service_returns_nothing_for_an_unknown_scheme():
    service = IngestService(IngestConfig())
    assert asyncio.run(service.fetch_content("gitlab:a/b@c:d.go")) is None
    assert asyncio.run(service.fetch_content("не ссылка")) is None


def test_service_builds_refs_for_untouched_repo_files():
    """Тул `get_file` должен доставать и то, чего в изменении не было."""
    service = IngestService(IngestConfig())
    bundle = go_bundle()
    ref = service.content_ref_for(bundle, "internal/never/touched.go")
    assert ref == f"github:acme/courier@{bundle.head_ref}:internal/never/touched.go"


def test_no_ref_without_a_repo_or_head():
    service = IngestService(IngestConfig())
    assert service.content_ref_for(go_bundle(repo=None), "a.go") is None
    assert service.content_ref_for(go_bundle(head_ref=None), "a.go") is None


# --------------------------------------------------------------------------- #
# разбор диффа
# --------------------------------------------------------------------------- #

def test_head_lines_skip_removed_lines():
    """Удалённой строки в новой версии файла нет — ей неоткуда взять номер."""
    patch = "@@ -10,3 +10,3 @@\n context\n-удалили\n+добавили\n tail\n"
    assert head_lines_from_patch(patch) == {10: "context", 11: "добавили", 12: "tail"}


def test_added_file_patch_covers_the_whole_file():
    lines = GO_MAIN.splitlines()
    patch = f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)
    assert head_lines_from_patch(patch) == dict(enumerate(lines, start=1))


def test_garbage_patch_yields_nothing_instead_of_raising():
    assert head_lines_from_patch("это не дифф") == {}
    assert added_line_ranges("это не дифф") == []


# --------------------------------------------------------------------------- #
# отказы источника
# --------------------------------------------------------------------------- #

class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Failed(Exception):
    def __init__(self, status: int | None) -> None:
        super().__init__("исходное сообщение клиента")
        if status is not None:
            self.response = _Response(status)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, "не найден"),
        (401, "INGEST_GITHUB__TOKEN"),
        (403, "INGEST_GITHUB__TOKEN"),
        (429, "лимит"),
        (500, "GitHub ответил 500"),
    ],
)
def test_github_failures_explain_what_to_fix(status, expected):
    """Голый repr исключения клиента уходил прямо в ответ API и ничего не объяснял."""
    from avito_reviewer.ingest.providers.github import _describe

    message = _describe(_Failed(status), "acme", "courier", 7)
    assert expected in message
    assert "acme/courier#7" in message


def test_failure_without_a_response_keeps_the_original_text():
    from avito_reviewer.ingest.providers.github import _describe

    assert "исходное сообщение клиента" in _describe(_Failed(None), "acme", "courier", 7)


# --------------------------------------------------------------------------- #
# политика повторов
# --------------------------------------------------------------------------- #

def _github_response(status: int):
    import httpx
    from githubkit.response import Response

    return Response(httpx.Response(status, request=httpx.Request("GET", "https://api.github.com/x")), object)


def _retry_decision():
    from avito_reviewer.config import GitHubConfig
    from avito_reviewer.ingest.providers.github import GitHubProvider

    return GitHubProvider(GitHubConfig())._gh.config.auto_retry


def test_rate_limit_fails_fast_instead_of_sleeping_it_off():
    """Штатная политика githubkit ждёт `retry_after` — до часа на анонимном ключе.

    Запрос ревьюера повис бы вместо внятной ошибки. Ждать лимит — дело
    вызывающего кода, а не блокирующего HTTP-вызова.
    """
    from datetime import timedelta

    from githubkit.exception import RateLimitExceeded

    limited = RateLimitExceeded(_github_response(403), timedelta(seconds=3600))
    assert _retry_decision()(limited, 0).do_retry is False


def test_server_errors_are_still_retried():
    """Пятисотка обычно разовая, и повтор дешевле, чем потерянная сдача."""
    from githubkit.exception import RequestFailed

    assert _retry_decision()(RequestFailed(_github_response(500)), 0).do_retry is True
