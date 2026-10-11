"""Poll ho.report for blocked-property pass/advance and improvement triggers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blast_lib.iterative_loop.blocked_property_metrics import (
    metric_name_for_property,
    property_metric_from_trial,
)
from blast_lib.iterative_loop.blocked_property_state import BlockedPropertyState
from blast_lib.iterative_loop.ho_report_local import count_scored_trials
from blast_lib.metrics import scored_trials
from blast_lib.parser import parse_ho_report


@dataclass(frozen=True)
class TargetAdvancedEvent:
    old_target_property: str
    new_target_property: str | None
    trial: dict[str, Any]
    reason: str = "current_target_passed"


@dataclass(frozen=True)
class BlockedPropertyImprovementTrigger:
    trial: dict[str, Any]
    target_property: str
    metric_name: str
    candidate_property_metric: float
    incumbent_before: float
    iteration: int | None


class BlockedPropertyImprovementWatcher:
    """
    Tracks scored trial count; evaluates only newly completed trials.

    Per trial: update pass state → target pass/advance (no recenter) → else metric improvement.
    """

    def __init__(
        self,
        report_path: Path,
        *,
        state: BlockedPropertyState,
        incumbent_property_obj: float | None,
        improvement_tolerance: float,
    ) -> None:
        self.report_path = report_path
        self.state = state
        self.incumbent_property_obj = incumbent_property_obj
        self.improvement_tolerance = improvement_tolerance
        self._scored_seen = count_scored_trials(report_path) if report_path.is_file() else 0
        self.last_improvement: BlockedPropertyImprovementTrigger | None = None
        self.last_target_advanced: TargetAdvancedEvent | None = None

    def reset_baseline(self) -> None:
        """After archiving ho.report — next poll treats all trials in fresh report as new."""
        self._scored_seen = 0
        self.last_improvement = None

    def sync_baseline_to_report(self) -> None:
        if self.report_path.is_file():
            self._scored_seen = count_scored_trials(self.report_path)
        else:
            self._scored_seen = 0

    def poll(self) -> BlockedPropertyImprovementTrigger | None:
        """
        Process new trials; mutate ``self.state``. Returns improvement trigger if any
        (pass/advance events are stored on ``last_target_advanced``).
        """
        if not self.report_path.is_file():
            return None
        count = count_scored_trials(self.report_path)
        if count <= self._scored_seen:
            return None

        trials = scored_trials(parse_ho_report(self.report_path))
        new_trials = trials[self._scored_seen :]
        trigger: BlockedPropertyImprovementTrigger | None = None

        for trial in new_trials:
            self.state.ingest_trial(trial)
            self.state.discover_target_if_needed()

            if self.state.all_passed():
                self._scored_seen = count
                return None

            target = self.state.target_property
            if target is None:
                continue

            if self.state.target_passed(trial):
                old, new = self.state.advance_after_target_passed()
                self.last_target_advanced = TargetAdvancedEvent(
                    old_target_property=old or target,
                    new_target_property=new,
                    trial=trial,
                )
                self.incumbent_property_obj = None
                continue

            metric = property_metric_from_trial(trial, target)
            if metric is None:
                continue

            if self.incumbent_property_obj is None:
                self.incumbent_property_obj = metric
                continue

            threshold = self.incumbent_property_obj - self.improvement_tolerance
            if metric < threshold:
                trigger = BlockedPropertyImprovementTrigger(
                    trial=trial,
                    target_property=target,
                    metric_name=metric_name_for_property(target),
                    candidate_property_metric=metric,
                    incumbent_before=self.incumbent_property_obj,
                    iteration=trial.get("iteration"),
                )
                self.incumbent_property_obj = metric
                break

        self._scored_seen = count
        if trigger is not None:
            self.last_improvement = trigger
        return trigger
