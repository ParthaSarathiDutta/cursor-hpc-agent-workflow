"""Persistent JSON state for the iterative fitting loop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from blast_lib.config_types import REPO_ROOT, UIConfig


class Phase(StrEnum):
    IDLE = "IDLE"
    SUBMITTING = "SUBMITTING"
    WAITING_FOR_JOB = "WAITING_FOR_JOB"
    ANALYZING_BEST_SET = "ANALYZING_BEST_SET"
    UPDATING_RANGES = "UPDATING_RANGES"
    STARTING_NEXT_CYCLE = "STARTING_NEXT_CYCLE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


TERMINAL_PHASES = frozenset({Phase.IDLE, Phase.COMPLETED, Phase.FAILED, Phase.STOPPED})

ACTIVE_PHASES = frozenset(
    {
        Phase.SUBMITTING,
        Phase.WAITING_FOR_JOB,
        Phase.ANALYZING_BEST_SET,
        Phase.UPDATING_RANGES,
        Phase.STARTING_NEXT_CYCLE,
    }
)


@dataclass
class IterativeLoopState:
    phase: str = Phase.IDLE
    run_folder: str = ""
    walltime: str = "00:10:00"
    total_cycles: int = 1
    current_cycle: int = 0
    active_job_id: str | None = None
    slurm_state: str | None = None
    last_completed_cycle: int = 0
    last_best_score: float | None = None
    last_best_iteration: int | None = None
    last_range_update: str | None = None
    scored_trial_count_before: int | None = None
    scored_trial_count_after: int | None = None
    error: str | None = None
    status_message: str = ""
    updated_at: str = ""
    workflow_id: str = ""

    def remaining_cycles(self) -> int:
        if self.total_cycles <= 0:
            return 0
        done = self.last_completed_cycle
        if self.phase in (Phase.COMPLETED,):
            return 0
        if self.current_cycle > 0:
            return max(0, self.total_cycles - self.current_cycle + 1)
        return self.total_cycles - done

    def touch(self, **kwargs: Any) -> None:
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.updated_at = datetime.now(timezone.utc).isoformat()


def _state_path(config: UIConfig) -> Path:
    return config.iterative_loop_state_file


def load_state(config: UIConfig) -> IterativeLoopState:
    path = _state_path(config)
    if not path.is_file():
        return IterativeLoopState()
    raw = json.loads(path.read_text())
    fields = IterativeLoopState.__dataclass_fields__
    return IterativeLoopState(**{k: v for k, v in raw.items() if k in fields})


def save_state(config: UIConfig, state: IterativeLoopState) -> None:
    path = _state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not state.updated_at:
        state.updated_at = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2))
    tmp.replace(path)


def begin_workflow(
    config: UIConfig,
    *,
    run_folder: str,
    walltime: str,
    total_cycles: int,
) -> IterativeLoopState:
    import uuid

    state = IterativeLoopState(
        phase=Phase.SUBMITTING,
        run_folder=run_folder,
        walltime=walltime,
        total_cycles=total_cycles,
        current_cycle=1,
        active_job_id=None,
        last_completed_cycle=0,
        error=None,
        status_message="Submitting job…",
        workflow_id=str(uuid.uuid4()),
    )
    state.touch()
    save_state(config, state)
    return state


def request_stop(config: UIConfig) -> IterativeLoopState:
    state = load_state(config)
    if state.phase in ACTIVE_PHASES:
        state.touch(phase=Phase.STOPPED, status_message="Stopped by user.", error=None)
    else:
        state.touch(phase=Phase.STOPPED, status_message="Stopped.")
    save_state(config, state)
    return state


def default_state_path() -> Path:
    return REPO_ROOT / ".cursor" / "status" / "iterative_loop.json"
