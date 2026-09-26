"""Persistent JSON state for the iterative fitting loop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from blast_lib.config_types import REPO_ROOT, UIConfig


class Phase(StrEnum):
    IDLE = "IDLE"
    SUBMITTING = "SUBMITTING"
    QUEUED_ON_NERSC = "QUEUED_ON_NERSC"
    RUNNING_ON_NERSC = "RUNNING_ON_NERSC"
    RUNNING_INTERACTIVE = "RUNNING_INTERACTIVE"
    WAITING_FOR_JOB = "WAITING_FOR_JOB"  # legacy; unused in interactive loop
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
        Phase.QUEUED_ON_NERSC,
        Phase.RUNNING_ON_NERSC,
        Phase.RUNNING_INTERACTIVE,
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
    interactive_launch_started: bool = False
    last_launch_returncode: int | None = None
    last_slurm_elapsed_sec: int | None = None
    stop_requested: bool = False
    execution_mode: str = "interactive"  # interactive | batch
    nersc_workflow_status: str | None = None

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


def begin_batch_workflow(
    config: UIConfig,
    *,
    run_folder: str,
    walltime: str,
    total_cycles: int,
    workflow_id: str,
) -> IterativeLoopState:
    state = IterativeLoopState(
        phase=Phase.QUEUED_ON_NERSC,
        run_folder=run_folder,
        walltime=walltime,
        total_cycles=total_cycles,
        current_cycle=1,
        last_completed_cycle=0,
        error=None,
        status_message="Submitting Slurm dependency chain on NERSC…",
        workflow_id=workflow_id,
        execution_mode="batch",
        nersc_workflow_status="QUEUED",
        interactive_launch_started=False,
        stop_requested=False,
    )
    state.touch()
    save_state(config, state)
    return state


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
        status_message="Preparing interactive launch…",
        workflow_id=str(uuid.uuid4()),
        interactive_launch_started=False,
        stop_requested=False,
    )
    state.touch()
    save_state(config, state)
    return state


def request_stop(config: UIConfig) -> IterativeLoopState:
    from blast_lib.remote import RemoteError, ssh_exec

    state = load_state(config)
    if state.execution_mode == "batch" and state.run_folder:
        from blast_lib.iterative_loop.batch_submit_agent import cancel_remote_workflow

        try:
            cancel_remote_workflow(config, state.run_folder)
        except RemoteError:
            pass
        state.touch(
            phase=Phase.STOPPED,
            status_message="Stop requested — scancel sent for NERSC workflow jobs.",
            stop_requested=True,
            nersc_workflow_status="STOPPED",
        )
        save_state(config, state)
        return state

    if state.phase == Phase.RUNNING_INTERACTIVE:
        state.stop_requested = True
        cancel_msg = ""
        if state.active_job_id:
            try:
                ssh_exec(config, f"scancel {state.active_job_id}", timeout=20)
                cancel_msg = f" Sent scancel {state.active_job_id}."
            except RemoteError:
                cancel_msg = f" Could not scancel {state.active_job_id} (allocation may still run)."
        if state.interactive_launch_started:
            state.status_message = (
                "Stop requested — will not start another cycle."
                + cancel_msg
                + " Current interactive SSH session runs until the allocation ends."
            )
        else:
            state.phase = Phase.STOPPED
            state.status_message = "Stopped before interactive launch started."
        save_state(config, state)
        return state

    if state.phase in ACTIVE_PHASES:
        state.touch(phase=Phase.STOPPED, status_message="Stopped by user.", error=None, stop_requested=True)
    else:
        state.touch(phase=Phase.STOPPED, status_message="Stopped.", stop_requested=True)
    save_state(config, state)
    return state


def default_state_path() -> Path:
    return REPO_ROOT / ".cursor" / "status" / "iterative_loop.json"
