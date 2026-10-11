"""Persistent pass/reach state and target discovery for blocked-property improvement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from blast_lib.iterative_loop.hierarchy_pass_counts import (
    normalize_hierarchy,
    property_passed_in_trial,
)
from blast_lib.iterative_loop.blocked_property_metrics import property_stage_reached_in_trial

BLOCKED_PHASE_DISCOVERY = "TARGET_DISCOVERY"
BLOCKED_PHASE_OPTIMIZING = "OPTIMIZING"


@dataclass
class BlockedPropertyState:
    active_hierarchy: list[str]
    property_passed_ever: dict[str, bool] = field(default_factory=dict)
    property_reached_ever: dict[str, bool] = field(default_factory=dict)
    target_property: str | None = None
    phase: str = BLOCKED_PHASE_DISCOVERY

    def __post_init__(self) -> None:
        self.active_hierarchy = normalize_hierarchy(self.active_hierarchy)
        for prop in self.active_hierarchy:
            self.property_passed_ever.setdefault(prop, False)
            self.property_reached_ever.setdefault(prop, False)

    @classmethod
    def from_workflow(cls, wf: Any) -> BlockedPropertyState:
        hierarchy = normalize_hierarchy(getattr(wf, "active_hierarchy", None) or [])
        passed = dict(getattr(wf, "property_passed_ever", None) or {})
        reached = dict(getattr(wf, "property_reached_ever", None) or {})
        target = getattr(wf, "target_property", None) or None
        phase = getattr(wf, "blocked_property_phase", None) or BLOCKED_PHASE_DISCOVERY
        if target:
            phase = BLOCKED_PHASE_OPTIMIZING
        st = cls(
            active_hierarchy=hierarchy,
            property_passed_ever=passed,
            property_reached_ever=reached,
            target_property=target,
            phase=phase,
        )
        return st

    def apply_to_workflow(self, wf: Any) -> None:
        wf.property_passed_ever = dict(self.property_passed_ever)
        wf.property_reached_ever = dict(self.property_reached_ever)
        wf.target_property = self.target_property
        wf.blocked_property_phase = self.phase

    def all_passed(self) -> bool:
        return all(self.property_passed_ever.get(p) for p in self.active_hierarchy)

    def ingest_trial(self, trial: dict[str, Any]) -> None:
        for prop in self.active_hierarchy:
            if property_stage_reached_in_trial(trial, prop):
                self.property_reached_ever[prop] = True
            if property_passed_in_trial(trial, prop, self.active_hierarchy):
                self.property_passed_ever[prop] = True

    def discover_target_if_needed(self, *, require_reach: bool = True) -> str | None:
        """
        Assign target when in discovery.

        Initial discovery (require_reach=True) waits for stage evidence in trials.
        After a target passes (require_reach=False), the next first-unpassed property
        becomes the target even before it is reached in the fresh region report.
        """
        if self.target_property is not None:
            self.phase = BLOCKED_PHASE_OPTIMIZING
            return self.target_property
        for prop in self.active_hierarchy:
            if self.property_passed_ever.get(prop):
                continue
            if require_reach and not self.property_reached_ever.get(prop):
                continue
            self.target_property = prop
            self.phase = BLOCKED_PHASE_OPTIMIZING
            return prop
        self.phase = BLOCKED_PHASE_DISCOVERY
        return None

    def target_passed(self, trial: dict[str, Any]) -> bool:
        if not self.target_property:
            return False
        return property_passed_in_trial(trial, self.target_property, self.active_hierarchy)

    def advance_after_target_passed(self) -> tuple[str | None, str | None]:
        if not self.target_property:
            return None, None
        old = self.target_property
        self.property_passed_ever[old] = True
        self.target_property = None
        self.phase = BLOCKED_PHASE_DISCOVERY
        nxt = self.discover_target_if_needed(require_reach=False)
        return old, nxt

    def first_blocked_for_display(self) -> str | None:
        for prop in self.active_hierarchy:
            if not self.property_passed_ever.get(prop):
                return prop
        return None
