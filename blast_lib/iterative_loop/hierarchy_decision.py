"""First-unpassed property detection and adjacent hierarchy swap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from blast_lib.iterative_loop.hierarchy_constants import (
    DECISION_ALL_PROPERTIES_PASSED,
    DECISION_NO_SWAPPABLE_PROPERTY,
    DECISION_SWITCH,
)
from blast_lib.iterative_loop.hierarchy_pass_counts import (
    normalize_hierarchy,
    property_pass_counts,
)


@dataclass(frozen=True)
class HierarchyWindowDecision:
    decision: str
    active_hierarchy: list[str]
    target_hierarchy: list[str]
    pass_counts: dict[str, int]
    first_unpassed_property: str | None
    swapped_with_property: str | None
    trials_in_window: int


def first_unpassed_property(active_hierarchy: list[str], pass_counts: dict[str, int]) -> str | None:
    hierarchy = normalize_hierarchy(active_hierarchy)
    for prop in hierarchy:
        if pass_counts.get(prop, 0) == 0:
            return prop
    return None


def swap_adjacent(hierarchy: list[str], prop: str) -> list[str]:
    """Move prop one position earlier (swap with immediate predecessor)."""
    h = list(normalize_hierarchy(hierarchy))
    prop = normalize_hierarchy([prop])[0]
    idx = h.index(prop)
    if idx == 0:
        raise ValueError(f"Cannot swap {prop!r} — no predecessor")
    out = h[:]
    out[idx - 1], out[idx] = out[idx], out[idx - 1]
    return out


def decide_after_observation_window(
    trials: list[dict[str, Any]],
    active_hierarchy: list[str],
) -> HierarchyWindowDecision:
    hierarchy = normalize_hierarchy(active_hierarchy)
    counts = property_pass_counts(trials, hierarchy)
    first = first_unpassed_property(hierarchy, counts)

    if first is None:
        return HierarchyWindowDecision(
            decision=DECISION_ALL_PROPERTIES_PASSED,
            active_hierarchy=hierarchy,
            target_hierarchy=hierarchy,
            pass_counts=counts,
            first_unpassed_property=None,
            swapped_with_property=None,
            trials_in_window=len(trials),
        )

    idx = hierarchy.index(first)
    if idx == 0:
        return HierarchyWindowDecision(
            decision=DECISION_NO_SWAPPABLE_PROPERTY,
            active_hierarchy=hierarchy,
            target_hierarchy=hierarchy,
            pass_counts=counts,
            first_unpassed_property=first,
            swapped_with_property=None,
            trials_in_window=len(trials),
        )

    predecessor = hierarchy[idx - 1]
    target = swap_adjacent(hierarchy, first)
    return HierarchyWindowDecision(
        decision=DECISION_SWITCH,
        active_hierarchy=hierarchy,
        target_hierarchy=target,
        pass_counts=counts,
        first_unpassed_property=first,
        swapped_with_property=predecessor,
        trials_in_window=len(trials),
    )
