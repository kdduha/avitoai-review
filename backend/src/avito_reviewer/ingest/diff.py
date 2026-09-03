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


def _with_file_header(patch_text: str) -> str:
    head = patch_text.lstrip()
    if head.startswith(("diff --git", "--- ")):
        return patch_text
    return f"--- a/patch\n+++ b/patch\n{patch_text}"


def added_line_ranges(patch_text: str) -> list[LineRange]:
    """Target-side line ranges a per-file patch adds or modifies (header optional)."""
    try:
        patch = PatchSet(_with_file_header(patch_text))
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
