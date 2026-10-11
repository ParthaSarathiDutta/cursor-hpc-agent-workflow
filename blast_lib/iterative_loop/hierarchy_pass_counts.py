"""Window-scoped property pass detection from ho.report trials."""

from __future__ import annotations

from typing import Any

from blast_lib.metrics import scored_trials
from blast_lib.parser import parse_ho_report
from blast_lib.trial_details import parse_property_blocks

from blast_lib.iterative_loop.hierarchy_constants import DEFAULT_ACTIVE_HIERARCHY


def normalize_hierarchy_property(name: str) -> str:
    n = name.strip().lower()
    if n in ("cohesive_e", "cohesive", "cohesiveenergy", "cohesive_energy"):
        return "ce"
    return n


def normalize_hierarchy(hierarchy: list[str] | tuple[str, ...] | None) -> list[str]:
    if not hierarchy:
        return list(DEFAULT_ACTIVE_HIERARCHY)
    return [normalize_hierarchy_property(p) for p in hierarchy]


def _trial_excluded_from_pass_evidence(trial: dict[str, Any]) -> bool:
    if trial.get("status") == "invalid":
        return True
    reason = (trial.get("reason") or "").lower()
    if "runtime error" in reason:
        return True
    if "invalid parameter" in reason:
        return True
    return False


def _blocks_for_stage(blocks: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    stage = normalize_hierarchy_property(stage)
    return [
        b
        for b in blocks
        if normalize_hierarchy_property(str(b.get("stage") or "")) == stage and not b.get("missing")
    ]


def _stage_computed(block: dict[str, Any]) -> bool:
    if block.get("missing"):
        return False
    if block.get("checkpoints"):
        return True
    metrics = block.get("metrics") or {}
    return bool(metrics)


def property_passed_in_trial(
    trial: dict[str, Any],
    prop: str,
    active_hierarchy: list[str],
) -> bool:
    """
    True when there is positive evidence the property passed under early-exit semantics.
    """
    if _trial_excluded_from_pass_evidence(trial):
        return False

    prop = normalize_hierarchy_property(prop)
    hierarchy = normalize_hierarchy(active_hierarchy)
    if prop not in hierarchy:
        return False

    blocks = parse_property_blocks(trial.get("stage_lines") or [])
    idx = hierarchy.index(prop)
    later_props = hierarchy[idx + 1 :]

    for block in _blocks_for_stage(blocks, prop):
        if block.get("passed") is True:
            return True

    for later in later_props:
        for block in _blocks_for_stage(blocks, later):
            if _stage_computed(block):
                return True

    reason = (trial.get("reason") or "").lower()
    if "completed all stages" in reason:
        return True

    return False


def property_pass_counts(
    trials: list[dict[str, Any]],
    active_hierarchy: list[str],
) -> dict[str, int]:
    """Number of trials in the window where each property passed (>=1 means satisfied)."""
    hierarchy = normalize_hierarchy(active_hierarchy)
    counts = {p: 0 for p in hierarchy}
    for trial in trials:
        for prop in hierarchy:
            if property_passed_in_trial(trial, prop, hierarchy):
                counts[prop] += 1
    return counts


def trials_in_observation_window(
    report_path,
    *,
    scored_trial_start_index: int,
) -> list[dict[str, Any]]:
    from pathlib import Path

    path = Path(report_path)
    if not path.is_file():
        return []
    all_scored = scored_trials(parse_ho_report(path))
    start = max(0, int(scored_trial_start_index))
    if start >= len(all_scored):
        return []
    return all_scored[start:]
