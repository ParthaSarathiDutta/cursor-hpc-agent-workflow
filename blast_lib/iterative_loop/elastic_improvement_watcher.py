"""Poll ho.report for elastic improvements vs incumbent (new scored trials only)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blast_lib.iterative_loop.ho_report_local import (
    count_scored_trials,
    elastic_values_obj_from_trial,
)
from blast_lib.metrics import scored_trials
from blast_lib.parser import parse_ho_report


@dataclass(frozen=True)
class ImprovementTrigger:
    trial: dict
    candidate_elastic_obj: float
    iteration: int | None


class ElasticImprovementWatcher:
    """Tracks scored trial count; evaluates only newly completed trials."""

    def __init__(
        self,
        report_path: Path,
        *,
        incumbent_elastic_obj: float,
        improvement_tolerance: float,
    ) -> None:
        self.report_path = report_path
        self.incumbent_elastic_obj = incumbent_elastic_obj
        self.improvement_tolerance = improvement_tolerance
        self._scored_seen = count_scored_trials(report_path) if report_path.is_file() else 0
        self.last_trigger: ImprovementTrigger | None = None

    def reset_baseline(self) -> None:
        """After archiving ho.report — next poll treats all trials as new."""
        self._scored_seen = 0
        self.last_trigger = None

    def sync_baseline_to_report(self) -> None:
        if self.report_path.is_file():
            self._scored_seen = count_scored_trials(self.report_path)
        else:
            self._scored_seen = 0

    def poll(self) -> ImprovementTrigger | None:
        if not self.report_path.is_file():
            return None
        count = count_scored_trials(self.report_path)
        if count <= self._scored_seen:
            return None

        trials = scored_trials(parse_ho_report(self.report_path))
        new_trials = trials[self._scored_seen :]
        threshold = self.incumbent_elastic_obj - self.improvement_tolerance

        trigger: ImprovementTrigger | None = None
        for trial in new_trials:
            obj = elastic_values_obj_from_trial(trial)
            if obj is None:
                continue
            if obj < threshold:
                trigger = ImprovementTrigger(
                    trial=trial,
                    candidate_elastic_obj=obj,
                    iteration=trial.get("iteration"),
                )
                break

        self._scored_seen = count
        if trigger is not None:
            self.last_trigger = trigger
        return trigger
