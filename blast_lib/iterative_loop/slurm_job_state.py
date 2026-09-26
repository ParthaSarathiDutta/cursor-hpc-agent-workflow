"""Local sacct job state queries (Perlmutter orchestrator; no SSH)."""

from __future__ import annotations

import subprocess

# Slurm State field may include suffixes, e.g. TIMEOUT+ or CANCELLED by 96380
_TERMINAL_BASE = frozenset(
    {
        "COMPLETED",
        "TIMEOUT",
        "FAILED",
        "CANCELLED",
        "OUT_OF_MEMORY",
        "NODE_FAIL",
        "PREEMPTED",
        "BOOT_FAIL",
        "DEADLINE",
    }
)

_GPU_ALLOCATION_OK = frozenset({"COMPLETED", "TIMEOUT"})


def normalize_slurm_state(raw: str) -> str:
    text = (raw or "").strip().upper()
    if not text:
        return ""
    token = text.split()[0]
    return token.split("+")[0]


def slurm_state_is_terminal(state: str) -> bool:
    base = normalize_slurm_state(state)
    return base in _TERMINAL_BASE


def slurm_state_ok_after_gpu_walltime(state: str) -> bool:
    """Allocation ended as expected (full walltime timeout or clean completion)."""
    base = normalize_slurm_state(state)
    return base in _GPU_ALLOCATION_OK


def fetch_sacct_job_state_local(job_id: str) -> str | None:
    jid = job_id.strip()
    if not jid.isdigit():
        return None
    cmd = ["sacct", "-j", jid, "-X", "--format=State", "-P", "-n"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    if not out:
        return None
    return normalize_slurm_state(out.splitlines()[0])
