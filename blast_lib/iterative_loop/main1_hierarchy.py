"""Parse and reorder LIVE property blocks in run-folder main1.py."""

from __future__ import annotations

import re
from dataclasses import dataclass

from blast_lib.iterative_loop.hierarchy_pass_counts import normalize_hierarchy, normalize_hierarchy_property

_LIVE_PROP_RE = re.compile(
    r"^(?P<indent>\s*)prop\s*=\s*['\"](?P<name>[A-Za-z_]+)['\"]\s*$"
)
_FOOTER_RETURN_RE = re.compile(r"^\s*return\s+HO\.lastfinalobj\s*\(")
_FOOTER_RUNTIME_RE = re.compile(
    r"^blast\.runtime\s*\[\s*['\"]objective['\"]\s*\]\s*="
)


@dataclass(frozen=True)
class Main1PropertyBlock:
    name: str
    start_line: int  # inclusive, 0-based
    end_line: int  # exclusive


class Main1HierarchyError(ValueError):
    """Ambiguous or invalid main1.py for hierarchy transforms."""


def _line_is_commented(line: str) -> bool:
    stripped = line.lstrip()
    return not stripped or stripped.startswith("#")


def _find_objective_footer_start(lines: list[str], *, after_line: int) -> int:
    """
    Line index where the post-property objective tail begins (inclusive).

    BLAST run-folder ``main1.py`` files register ``objective`` after all property
    stages; the last property block must not swallow that tail when it is the final
    live ``prop =`` assignment in the file.
    """
    candidates: list[int] = []
    for i, line in enumerate(lines):
        if i <= after_line:
            continue
        if _FOOTER_RETURN_RE.match(line) or _FOOTER_RUNTIME_RE.match(line):
            candidates.append(i)
    if not candidates:
        return len(lines)
    return min(candidates)


def extract_live_property_blocks(source: str) -> list[Main1PropertyBlock]:
    """
    Identify LIVE ``prop = '…'`` sections in source order.

    A block runs from a live prop assignment through the line before the next live prop assignment.
    """
    lines = source.splitlines()
    prop_starts: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        if _line_is_commented(line):
            continue
        m = _LIVE_PROP_RE.match(line)
        if not m:
            continue
        name = normalize_hierarchy_property(m.group("name"))
        prop_starts.append((i, name, m.group("indent")))

    if not prop_starts:
        raise Main1HierarchyError("No live prop = assignments found in main1.py")

    names = [n for _i, n, _ind in prop_starts]
    if len(set(names)) != len(names):
        raise Main1HierarchyError(f"Duplicate live property assignments: {names!r}")

    last_prop_start = prop_starts[-1][0]
    footer_start = _find_objective_footer_start(lines, after_line=last_prop_start)

    blocks: list[Main1PropertyBlock] = []
    for j, (start, name, _indent) in enumerate(prop_starts):
        if j + 1 < len(prop_starts):
            end = prop_starts[j + 1][0]
        else:
            end = footer_start
        blocks.append(Main1PropertyBlock(name=name, start_line=start, end_line=end))
    return blocks


def live_property_order(source: str) -> list[str]:
    return [b.name for b in extract_live_property_blocks(source)]


def validate_live_order_matches(source: str, active_hierarchy: list[str]) -> None:
    live = live_property_order(source)
    expected = normalize_hierarchy(active_hierarchy)
    if live != expected:
        raise Main1HierarchyError(
            f"main1.py live property order {live!r} does not match active hierarchy {expected!r}"
        )


def _slice_block(lines: list[str], block: Main1PropertyBlock) -> list[str]:
    return lines[block.start_line : block.end_line]


def reorder_main1_to_hierarchy(source: str, target_hierarchy: list[str]) -> str:
    """
    Reorder LIVE property blocks to ``target_hierarchy`` (must be a permutation of live props).
    """
    blocks = extract_live_property_blocks(source)
    lines = source.splitlines(keepends=True)
    if not lines:
        raise Main1HierarchyError("Empty main1.py")

    live_names = [b.name for b in blocks]
    target = normalize_hierarchy(target_hierarchy)
    if sorted(target) != sorted(live_names):
        raise Main1HierarchyError(
            f"target hierarchy {target!r} is not a permutation of live properties {live_names!r}"
        )
    if len(set(live_names)) != len(live_names):
        raise Main1HierarchyError(f"Duplicate live property names: {live_names!r}")

    by_name = {b.name: b for b in blocks}
    last_prop_start = max(b.start_line for b in blocks)
    footer_start = _find_objective_footer_start(lines, after_line=last_prop_start)
    prefix = lines[: blocks[0].start_line]
    suffix = lines[footer_start:]

    middle: list[str] = []
    for name in target:
        block = by_name[name]
        middle.extend(_slice_block(lines, block))

    if not middle:
        raise Main1HierarchyError("No property block content to reorder")

    return "".join(prefix + middle + suffix)


def apply_adjacent_swap_to_main1(
    source: str,
    *,
    active_hierarchy: list[str],
    first_unpassed: str,
) -> tuple[str, list[str]]:
    """
    Swap ``first_unpassed`` with its predecessor; validate before/after order.
    """
    from blast_lib.iterative_loop.hierarchy_decision import swap_adjacent

    validate_live_order_matches(source, active_hierarchy)
    target = swap_adjacent(active_hierarchy, first_unpassed)
    updated = reorder_main1_to_hierarchy(source, target)
    validate_live_order_matches(updated, target)
    return updated, target


def assert_target_order_in_source(source: str, target_hierarchy: list[str]) -> None:
    """Validate executable order by live prop line sequence."""
    validate_live_order_matches(source, target_hierarchy)
