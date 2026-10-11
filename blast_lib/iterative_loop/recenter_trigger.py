"""Recenter scheduling policy (orthogonal to selection_strategy)."""

from __future__ import annotations

RECENTER_FIXED_CYCLE = "fixed_cycle"
RECENTER_IMPROVEMENT = "improvement"
VALID_RECENTER_TRIGGERS = frozenset({RECENTER_FIXED_CYCLE, RECENTER_IMPROVEMENT})

DEFAULT_IMPROVEMENT_TOLERANCE = 0.01
DEFAULT_MAX_REGIONS = 50

# Not scientifically validated on Perlmutter repeatability yet — override in strategy.json.
TOLERANCE_NOT_VALIDATED_NOTE = (
    "improvement_tolerance default 0.01 is a practical placeholder; "
    "verify ho.report elastic.values.obj repeatability before production runs."
)
