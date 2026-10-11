"""Mirror NERSC .agentic_loop/workflow.json into Mac iterative_loop state."""

from __future__ import annotations

import json
import shlex

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.remote_workflow import WorkflowPhase, WorkflowStatus, workflow_json_path
from blast_lib.iterative_loop.state import IterativeLoopState, Phase, load_state, save_state
from blast_lib.remote import RemoteError, ssh_exec


def fetch_remote_workflow_json(config: UIConfig, run_folder: str) -> dict | None:
    path = workflow_json_path(run_folder)
    cmd = f"cat {shlex.quote(path.as_posix())} 2>/dev/null || true"
    try:
        raw = ssh_exec(config, cmd, timeout=30).strip()
    except RemoteError:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def mirror_remote_to_local(config: UIConfig, run_folder: str) -> IterativeLoopState:
    data = fetch_remote_workflow_json(config, run_folder)
    state = load_state(config)
    if not data:
        return state

    status = data.get("status", "")
    total = int(data.get("total_cycles") or state.total_cycles or 1)
    cycles = data.get("cycles") or []
    completed = sum(1 for c in cycles if c.get("range_status") == "COMPLETED")
    current = min(completed + 1, total) if status in (WorkflowStatus.RUNNING, WorkflowStatus.QUEUED) else completed

    phase_map = {
        WorkflowStatus.QUEUED: Phase.QUEUED_ON_NERSC,
        WorkflowStatus.RUNNING: Phase.RUNNING_ON_NERSC,
        WorkflowStatus.COMPLETED: Phase.COMPLETED,
        WorkflowStatus.FAILED: Phase.FAILED,
        WorkflowStatus.CANCELLED: Phase.STOPPED,
        WorkflowStatus.STOPPED: Phase.STOPPED,
    }
    phase = phase_map.get(status, state.phase)

    last_best_score = None
    last_best_iteration = None
    last_range = None
    for c in reversed(cycles):
        if c.get("range_status") == "COMPLETED":
            last_best_score = c.get("best_score")
            last_best_iteration = c.get("best_iteration")
            last_range = "COMPLETED"
            break
        if c.get("range_status") == "FAILED":
            last_range = "FAILED"
            break

    active_job = data.get("current_interactive_job_id") or data.get("orchestrator_job_id")
    if not active_job:
        for c in reversed(cycles):
            if c.get("range_job_id") and c.get("range_status") not in ("COMPLETED", "FAILED"):
                active_job = c.get("range_job_id")
                break
            if c.get("gpu_job_id") and not c.get("range_status"):
                active_job = c.get("gpu_job_id")
                break

    remote_phase = data.get("phase") or ""
    mode = "orchestrator" if data.get("orchestrator_job_id") else "batch"

    state.touch(
        execution_mode=mode,
        run_folder=data.get("run_folder") or run_folder,
        walltime=data.get("walltime") or state.walltime,
        total_cycles=total,
        current_cycle=current or state.current_cycle,
        last_completed_cycle=completed,
        phase=phase,
        workflow_id=data.get("workflow_id") or state.workflow_id,
        status_message=data.get("status_message") or "",
        error=data.get("error"),
        last_best_score=last_best_score,
        last_best_iteration=last_best_iteration,
        last_range_update=last_range,
        active_job_id=active_job,
        slurm_state=status,
        nersc_workflow_status=status,
    )
    if remote_phase in WorkflowPhase.__dict__.values():
        state.status_message = data.get("status_message") or state.status_message
    if data.get("orchestrator_job_id"):
        state.active_job_id = data.get("current_interactive_job_id") or data.get("orchestrator_job_id")
    save_state(config, state)
    return state
