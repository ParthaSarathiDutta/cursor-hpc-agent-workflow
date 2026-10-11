"""Observation window timing and pass-count evaluation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from blast_lib.iterative_loop.hierarchy_decision import HierarchyWindowDecision, decide_after_observation_window
from blast_lib.iterative_loop.hierarchy_pass_counts import trials_in_observation_window
from blast_lib.iterative_loop.ho_report_local import count_scored_trials


@dataclass
class ObservationWindowState:
    observation_window_index: int
    window_started_at_monotonic: float
    window_started_at_iso: str
    scored_trial_start_index: int


class HierarchyObservationWindow:
    def __init__(
        self,
        report_path: Path,
        *,
        observation_window_sec: float,
        active_hierarchy: list[str],
        observation_window_index: int = 0,
        scored_trial_start_index: int = 0,
        window_started_monotonic: float | None = None,
    ) -> None:
        self.report_path = report_path
        self.observation_window_sec = float(observation_window_sec)
        self.active_hierarchy = list(active_hierarchy)
        mono = window_started_monotonic if window_started_monotonic is not None else time.monotonic()
        self.state = ObservationWindowState(
            observation_window_index=observation_window_index,
            window_started_at_monotonic=mono,
            window_started_at_iso=datetime.now(timezone.utc).isoformat(),
            scored_trial_start_index=scored_trial_start_index,
        )

    def elapsed_sec(self) -> float:
        return time.monotonic() - self.state.window_started_at_monotonic

    def window_is_due(self) -> bool:
        return self.elapsed_sec() >= self.observation_window_sec

    def window_trials(self) -> list:
        return trials_in_observation_window(
            self.report_path,
            scored_trial_start_index=self.state.scored_trial_start_index,
        )

    def evaluate_if_due(self) -> HierarchyWindowDecision | None:
        if not self.window_is_due():
            return None
        trials = self.window_trials()
        return decide_after_observation_window(trials, self.active_hierarchy)

    def begin_next_window(self) -> None:
        idx = count_scored_trials(self.report_path) if self.report_path.is_file() else 0
        self.state = ObservationWindowState(
            observation_window_index=self.state.observation_window_index + 1,
            window_started_at_monotonic=time.monotonic(),
            window_started_at_iso=datetime.now(timezone.utc).isoformat(),
            scored_trial_start_index=idx,
        )

    def sync_scored_start_to_current_report(self) -> None:
        """On resume, align start index without resetting window clock."""
        idx = count_scored_trials(self.report_path) if self.report_path.is_file() else 0
        self.state.scored_trial_start_index = idx
