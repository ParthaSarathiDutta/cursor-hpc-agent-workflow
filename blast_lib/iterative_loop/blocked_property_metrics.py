"""Scalar improvement metrics per hierarchy property (ho.report trial blocks)."""

from __future__ import annotations

from typing import Any

from blast_lib.iterative_loop.hierarchy_pass_counts import normalize_hierarchy_property
from blast_lib.trial_details import parse_property_blocks

# Metric field names for provenance (not necessarily ho.report keys for eos).
METRIC_LATTICE = "values.obj"
METRIC_CE = "values.obj"
METRIC_EOS = "eos.composite"
METRIC_PHONON = "ceil.maxAE%"
METRIC_ELASTIC = "values.obj"


def metric_name_for_property(prop: str) -> str:
    prop = normalize_hierarchy_property(prop)
    if prop == "eos":
        return METRIC_EOS
    if prop == "phonon":
        return METRIC_PHONON
    return METRIC_ELASTIC if prop == "elastic" else METRIC_LATTICE


def _blocks_for_stage(trial: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    stage = normalize_hierarchy_property(stage)
    return [
        b
        for b in parse_property_blocks(trial.get("stage_lines") or [])
        if normalize_hierarchy_property(str(b.get("stage") or "")) == stage and not b.get("missing")
    ]


def _eos_scalar(metrics: dict[str, Any]) -> float | None:
    shape = metrics.get("shape.obj")
    shift = metrics.get("shift.obj")
    if shape is None or shift is None:
        return None
    return max(float(shape), float(shift))


def property_metric_from_trial(trial: dict[str, Any], prop: str) -> float | None:
    """
    Extract the scalar used for improvement comparison for ``prop``.

    Smaller is better for all supported properties. Returns None if the trial
    did not compute the target stage.
    """
    prop = normalize_hierarchy_property(prop)
    blocks = _blocks_for_stage(trial, prop)
    if not blocks:
        return None
    metrics = blocks[-1].get("metrics") or {}

    if prop == "eos":
        return _eos_scalar(metrics)
    if prop == "phonon":
        raw = metrics.get("ceil.maxAE%")
        if raw is None:
            return None
        return float(raw)

    raw = metrics.get("values.obj")
    if raw is None:
        return None
    return float(raw)


def property_stage_reached_in_trial(trial: dict[str, Any], prop: str) -> bool:
    """True when the trial has a computed (non-missing) block for ``prop``."""
    return bool(_blocks_for_stage(trial, prop))
