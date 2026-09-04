from __future__ import annotations

from collections.abc import Iterable

from unidiff import PatchSet, UnidiffParseError

from avito_reviewer.ingest.models import LineRange


def _coalesce(numbers: Iterable[int]) -> list[LineRange]:
    ranges: list[LineRange] = []
    for n in sorted(set(numbers)):
        if ranges and n == ranges[-1].end + 1:
            ranges[-1].end = n
        else:
            ranges.append(LineRange(start=n, end=n))
    return ranges


def with_file_header(patch_text: str) -> str:
    head = patch_text.lstrip()
    if head.startswith(("diff --git", "--- ")):
        return patch_text
    return f"--- a/patch\n+++ b/patch\n{patch_text}"


def added_line_ranges(patch_text: str) -> list[LineRange]:
    """Target-side line ranges a per-file patch adds or modifies (header optional)."""
    try:
        patch = PatchSet(with_file_header(patch_text))
    except UnidiffParseError:
        return []
    numbers = [
        line.target_line_no
        for patched_file in patch
        for hunk in patched_file
        for line in hunk
        if line.is_added and line.target_line_no is not None
    ]
    return _coalesce(numbers)


def head_lines_from_patch(patch_text: str) -> dict[int, str]:
    """Head-side lines a per-file patch reveals, keyed by 1-based line number.

    Added and context lines only -- a removed line has no place in the head file.
    For a file the change added this covers the whole file; for a modified file it
    covers the hunks and the context around them, and the gaps between them are
    unknown rather than empty. Callers must not read a gap as an absence.
    """
    try:
        patch = PatchSet(with_file_header(patch_text))
    except UnidiffParseError:
        return {}
    return {
        line.target_line_no: line.value.rstrip("\n")
        for patched_file in patch
        for hunk in patched_file
        for line in hunk
        if line.target_line_no is not None and (line.is_added or line.is_context)
    }
