"""Authoritative iterative-loop workflow state on NERSC (<run_folder>/.agentic_loop/)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkflowStatus:
    """String constants (Python 3.8-safe on Perlmutter; no enum.StrEnum)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STOPPED = "STOPPED"


class WorkflowPhase:
    """Fine-grained orchestrator phase (stored in workflow.json)."""

    QUEUED = "QUEUED"
    AWAITING_SALLOC = "AWAITING_SALLOC"
    RUNNING_GPU = "RUNNING_GPU"
    VALIDATING = "VALIDATING"
    RUNNING_RANGE = "RUNNING_RANGE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


@dataclass
class CycleRecord:
    cycle: int
    gpu_job_id: str | None = None
    range_job_id: str | None = None
    scored_trials_before: int | None = None
    scored_trials_after: int | None = None
    last_slurm_elapsed_sec: int | None = None
    best_score: float | None = None
    best_iteration: int | None = None
    range_status: str | None = None  # PENDING | COMPLETED | FAILED
    error: str | None = None


@dataclass
class RemoteWorkflow:
    workflow_id: str
    run_folder: str
    walltime: str
    total_cycles: int
    status: str = WorkflowStatus.QUEUED
    phase: str = WorkflowPhase.QUEUED
    current_cycle: int = 0
    blast_root: str = ""
    blast_python: str = ""
    orchestrator_job_id: str | None = None
    current_interactive_job_id: str | None = None
    salloc_attempts: int = 0
    gpu_account: str = ""
    salloc_account: str = ""
    salloc_nodes: int = 2
    salloc_ntasks_per_node: int = 4
    salloc_gpus_per_task: int = 1
    salloc_gpus: int = 8
    salloc_qos: str = "interactive"
    created_at: str = ""
    updated_at: str = ""
    error: str | None = None
    status_message: str = ""
    cycles: list[CycleRecord] = field(default_factory=list)

    def touch(self, **kwargs: Any) -> None:
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def cycle_record(self, n: int) -> CycleRecord:
        for c in self.cycles:
            if c.cycle == n:
                return c
        rec = CycleRecord(cycle=n)
        self.cycles.append(rec)
        return rec

    def all_job_ids(self) -> list[str]:
        ids: list[str] = []
        if self.orchestrator_job_id:
            ids.append(self.orchestrator_job_id)
        if self.current_interactive_job_id:
            ids.append(self.current_interactive_job_id)
        for c in self.cycles:
            if c.gpu_job_id:
                ids.append(c.gpu_job_id)
            if c.range_job_id:
                ids.append(c.range_job_id)
        return ids


def agentic_loop_dir(run_folder: str | Path) -> Path:
    return Path(run_folder).expanduser().resolve() / ".agentic_loop"


def workflow_json_path(run_folder: str | Path) -> Path:
    return agentic_loop_dir(run_folder) / "workflow.json"


def cycle_before_path(run_folder: str | Path, cycle: int) -> Path:
    return agentic_loop_dir(run_folder) / f"cycle_{cycle}_before.json"


def cycle_range_result_path(run_folder: str | Path, cycle: int) -> Path:
    return agentic_loop_dir(run_folder) / f"cycle_{cycle}_range_result.json"


def save_workflow(path: Path, wf: RemoteWorkflow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not wf.created_at:
        wf.created_at = datetime.now(timezone.utc).isoformat()
    wf.touch()
    payload = asdict(wf)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def load_workflow(path: Path) -> RemoteWorkflow:
    raw = json.loads(path.read_text())
    cycles_raw = raw.pop("cycles", [])
    cycles = [CycleRecord(**c) for c in cycles_raw]
    fields = RemoteWorkflow.__dataclass_fields__
    wf = RemoteWorkflow(**{k: v for k, v in raw.items() if k in fields})
    wf.cycles = cycles
    return wf


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def is_active_status(status: str) -> bool:
    return status in (WorkflowStatus.QUEUED, WorkflowStatus.RUNNING)


def mark_workflow_orchestrator_crash(
    path: Path,
    exc: BaseException,
    *,
    respect_stopped: bool = True,
) -> None:
    """Set FAILED when the orchestrator dies unexpectedly (do not clobber STOPPED)."""
    if not path.is_file():
        return
    wf = load_workflow(path)
    if respect_stopped and wf.status == WorkflowStatus.STOPPED:
        return
    msg = str(exc).strip() or exc.__class__.__name__
    wf.status = WorkflowStatus.FAILED
    wf.phase = WorkflowPhase.FAILED
    wf.error = msg
    wf.status_message = f"Orchestrator crashed: {msg}"
    wf.current_interactive_job_id = None
    save_workflow(path, wf)


def is_active_phase(phase: str) -> bool:
    return phase in (
        WorkflowPhase.QUEUED,
        WorkflowPhase.AWAITING_SALLOC,
        WorkflowPhase.RUNNING_GPU,
        WorkflowPhase.VALIDATING,
        WorkflowPhase.RUNNING_RANGE,
    )
