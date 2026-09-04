"""Тесты слоя текстов артефактов.

Здесь проверяется главное расхождение с ядром: полного текста файла может не
быть вовсе. Всё, что ниже, — про то, чтобы неполнота была видна, а не
маскировалась под полный файл.
"""

from __future__ import annotations

import asyncio

from factories import GO_MAIN, added_diff, artifact, go_bundle, partial_artifact, texts_of

from avito_reviewer.ai.content import build_texts, from_artifact
from avito_reviewer.config import ContentConfig
from avito_reviewer.ingest import ArtifactRole, ChangeStatus


class Resolver:
    """Резолвер `content_ref` под контроль теста."""

    def __init__(self, bodies: dict[str, str] | None = None, fail: bool = False) -> None:
        self.bodies = bodies or {}
        self.fail = fail
        self.asked: list[str] = []

    async def fetch_content(self, content_ref: str) -> str | None:
        self.asked.append(content_ref)
        if self.fail:
            raise RuntimeError("upstream отказал")
        return self.bodies.get(content_ref.split(":")[-1])


# --------------------------------------------------------------------------- #
# откуда берётся текст
# --------------------------------------------------------------------------- #

def test_excerpt_is_used_as_the_whole_file():
    text = texts_of(go_bundle())[0]
    assert text.origin == "excerpt"
    assert text.partial is False
    assert text.line_numbers == list(range(1, len(text.lines) + 1))


def test_added_file_is_complete_from_its_diff():
    """Дифф нового файла содержит его целиком — это не фрагмент."""
    bundle = go_bundle()
    bundle.artifacts[0].excerpt = None
    text = texts_of(bundle)[0]

    assert text.origin == "diff"
    assert text.partial is False
    assert 'r.Get("/ping", handlePing)' in text.text


def test_modified_file_from_a_hunk_is_a_fragment():
    text = texts_of(go_bundle(artifacts=[partial_artifact("internal/store/pg.go")]))[0]

    assert text.origin == "diff"
    assert text.partial is True
    assert text.line_numbers == [40, 41, 42, 43]


def test_diff_covering_the_top_of_a_big_file_is_still_a_fragment():
    """Ханк может начинаться с первой строки — это не значит, что файл кончился."""
    head = artifact(
        "internal/big.go",
        text=None,
        diff="@@ -1,2 +1,3 @@\n package main\n+import \"log\"\n func main() {\n",
        status=ChangeStatus.MODIFIED,
        size_bytes=30_000,
    )
    text = from_artifact(head)

    assert text is not None
    assert text.line_numbers[0] == 1
    assert text.partial is True


def test_hunk_markers_are_stripped():
    """Цитата с `+` в начале не совпадёт с файлом, и валидатор её отвергнет."""
    text = texts_of(go_bundle(artifacts=[partial_artifact("internal/store/pg.go")]))[0]
    assert not any(line.startswith(("+", "-", "@@")) for line in text.lines)
    assert "\trows, err := s.db.Query(ctx, q)" in text.lines


def test_artifact_without_body_or_diff_is_dropped():
    empty = artifact("assets/logo.svg", text=None, lang=None)
    empty.diff = None
    assert from_artifact(empty) is None


# --------------------------------------------------------------------------- #
# дозагрузка тел
# --------------------------------------------------------------------------- #

def test_resolver_fills_in_a_missing_body():
    bundle = go_bundle(artifacts=[partial_artifact("internal/store/pg.go")])
    resolver = Resolver({"internal/store/pg.go": "package store\n" + "line\n" * 40})
    text = texts_of(bundle, resolver)[0]

    assert resolver.asked == ["github:acme/courier@head:internal/store/pg.go"]
    assert text.origin == "fetched"
    assert text.partial is False


def test_resolver_failure_falls_back_to_the_diff():
    """Один недоступный файл не должен стоить всей сдачи."""
    bundle = go_bundle(artifacts=[partial_artifact("internal/store/pg.go")])
    text = texts_of(bundle, Resolver(fail=True))[0]

    assert text.origin == "diff"
    assert text.partial is True


def test_fetch_budget_prefers_more_small_files_over_one_huge():
    bundle = go_bundle(
        artifacts=[
            partial_artifact("a.go", size_bytes=1_000),
            partial_artifact("b.go", size_bytes=2_000),
            partial_artifact("huge.go", size_bytes=300_000),
        ]
    )
    resolver = Resolver({"a.go": "x\n", "b.go": "y\n", "huge.go": "z\n"})
    asyncio.run(build_texts(bundle, resolver, config=ContentConfig(max_files=2)))

    assert [ref.split(":")[-1] for ref in resolver.asked] == ["a.go", "b.go"]


def test_files_over_the_size_cap_are_never_fetched():
    bundle = go_bundle(artifacts=[partial_artifact("huge.go", size_bytes=900_000)])
    resolver = Resolver({"huge.go": "x\n"})
    asyncio.run(build_texts(bundle, resolver, config=ContentConfig(max_file_bytes=400_000)))

    assert resolver.asked == []


# --------------------------------------------------------------------------- #
# что вообще попадает в анализ
# --------------------------------------------------------------------------- #

def test_noise_binaries_and_deletions_are_excluded():
    bundle = go_bundle(
        artifacts=[
            artifact("cmd/main.go", text=GO_MAIN),
            artifact("go.sum", text="x\n", role=ArtifactRole.NOISE),
            artifact("docs/plot.png", text=None, diff=None, is_binary=True, lang=None),
            artifact("old.go", text="x\n", status=ChangeStatus.REMOVED),
        ]
    )
    assert [text.path for text in texts_of(bundle)] == ["cmd/main.go"]


# --------------------------------------------------------------------------- #
# координаты
# --------------------------------------------------------------------------- #

def test_window_is_addressed_by_head_lines():
    text = texts_of(go_bundle(artifacts=[partial_artifact("internal/store/pg.go")]))[0]
    assert "s.db.Query" in text.window(41, 41)
    assert text.window(1, 39) == ""


def test_changed_ranges_are_summarised_for_the_prompt():
    text = from_artifact(
        artifact("a.go", text="a\nb\nc\nd\ne\n", changed=[(1, 3), (5, 5)], diff=added_diff("a\nb"))
    )
    assert text is not None
    assert text.changed_summary() == "1–3, 5"
