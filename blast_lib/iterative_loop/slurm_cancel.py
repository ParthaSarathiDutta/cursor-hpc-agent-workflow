"""Strict Slurm cancellation — explicit job IDs from workflow state only.

AgenticBLAST must NEVER run broad cancellation (scancel -u, by QOS/partition,
or grep squeue for generic interactive jobs). Unrelated user jobs on NERSC
must not be touched by Stop/cleanup.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any, Callable

_SLURM_JOB_ID_RE = re.compile(r"^\d+$")


def validate_slurm_job_id(job_id: str) -> str:
    """Return stripped numeric job id or raise ValueError."""
    text = (job_id or "").strip()
    if not _SLURM_JOB_ID_RE.match(text):
        raise ValueError(f"Refusing scancel: invalid Slurm job id {job_id!r}")
    return text


def scancel_argv(job_id: str) -> list[str]:
    """Build argv for ``scancel <jobid>`` (single explicit id only)."""
    return ["scancel", validate_slurm_job_id(job_id)]


def collect_orchestrator_workflow_cancel_ids(workflow: dict[str, Any]) -> list[str]:
    """
    Job ids eligible for orchestrator Stop — sourced only from workflow.json fields.
    """
    ids: list[str] = []
    for key in ("orchestrator_job_id", "current_interactive_job_id"):
        jid = workflow.get(key)
        if jid and str(jid).isdigit():
            ids.append(str(jid))
    for cycle in workflow.get("cycles") or []:
        if cycle.get("gpu_job_id") and cycle.get("range_status") != "COMPLETED":
            jid = cycle.get("gpu_job_id")
            if jid and str(jid).isdigit():
                ids.append(str(jid))
    # Preserve order, dedupe
    return list(dict.fromkeys(ids))


def collect_batch_workflow_cancel_ids(workflow: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for cycle in workflow.get("cycles") or []:
        for key in ("gpu_job_id", "range_job_id"):
            jid = cycle.get(key)
            if jid and str(jid).isdigit():
                ids.append(str(jid))
    return list(dict.fromkeys(ids))


def scancel_job_local(job_id: str) -> None:
    try:
        subprocess.run(scancel_argv(job_id), capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass


def scancel_jobs_via_ssh(
    ssh_exec: Callable[[str, float], str],
    job_ids: list[str],
    *,
    timeout: float = 15.0,
) -> list[str]:
    """Run ``scancel <id>`` for each validated id; return commands executed."""
    executed: list[str] = []
    for jid in job_ids:
        argv = scancel_argv(jid)
        cmd = " ".join(argv)
        ssh_exec(f"{cmd} 2>/dev/null || true", timeout)
        executed.append(cmd)
    return executed
