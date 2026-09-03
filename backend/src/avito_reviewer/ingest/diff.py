from __future__ import annotations

from collections.abc import Iterable

from unidiff import PatchSet, UnidiffParseError

from avito_reviewer.ingest.models import LineRange


def _coalesce(numbers: Iterable[int]) -> list[LineRange]:
    ordered = sorted(set(numbers))
    ranges: list[LineRange] = []
    for n in ordered:
        if ranges and n == ranges[-1].end + 1:
            ranges[-1].end = n
        else:
            ranges.append(LineRange(start=n, end=n))
    return ranges


def _ensure_file_header(patch_text: str) -> str:
    head = patch_text.lstrip()
    if head.startswith(("diff --git", "--- ")):
        return patch_text
    return f"--- a/patch\n+++ b/patch\n{patch_text}"


def added_line_ranges(patch_text: str) -> list[LineRange]:
    """Target-side line ranges that a per-file patch (header optional) adds or modifies."""
    try:
        patch = PatchSet(_ensure_file_header(patch_text))
    except UnidiffParseError:
        return []
    numbers: list[int] = []
    for patched_file in patch:
        for hunk in patched_file:
            numbers.extend(
                line.target_line_no
                for line in hunk
                if line.is_added and line.target_line_no is not None
            )
    return _coalesce(numbers)


def changed_ranges_by_path(diff_text: str) -> dict[str, list[LineRange]]:
    """Map each target path in a unified diff to its added/modified line ranges."""
    try:
        patch = PatchSet(diff_text)
    except UnidiffParseError:
        return {}
    result: dict[str, list[LineRange]] = {}
    for patched_file in patch:
        numbers = [
            line.target_line_no
            for hunk in patched_file
            for line in hunk
            if line.is_added and line.target_line_no is not None
        ]
        result[patched_file.path] = _coalesce(numbers)
    return result
