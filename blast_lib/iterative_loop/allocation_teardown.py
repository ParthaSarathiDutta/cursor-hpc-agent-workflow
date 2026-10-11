"""Wait for workflow-owned interactive allocations to reach terminal Slurm state."""

from __future__ import annotations

import time
from typing import Callable, Optional

from blast_lib.iterative_loop.slurm_cancel import scancel_job_local
from blast_lib.iterative_loop.slurm_job_state import fetch_sacct_job_state_local, slurm_state_is_terminal

PollSlurmJobStateFn = Callable[[str], Optional[str]]
SleepFn = Callable[[float], None]
ScancelFn = Callable[[str], None]


def wait_for_slurm_job_terminal(
    job_id: str | None,
    *,
    poll_fn: PollSlurmJobStateFn | None = None,
    sleep_fn: SleepFn | None = None,
    timeout_sec: float = 180.0,
    poll_interval_sec: float = 2.0,
) -> str | None:
    """Poll sacct until job is terminal or timeout. Returns final normalized state."""
    poll = poll_fn or fetch_sacct_job_state_local
    sleep = sleep_fn or time.sleep
    jid = (job_id or "").strip()
    if not jid.isdigit():
        return None
    deadline = time.monotonic() + max(1.0, timeout_sec)
    last: str | None = None
    while time.monotonic() < deadline:
        last = poll(jid)
        if last and slurm_state_is_terminal(last):
            return last
        sleep(poll_interval_sec)
    return poll(jid) or last


def drain_interactive_allocation(
    job_id: str | None,
    *,
    poll_fn: PollSlurmJobStateFn | None = None,
    sleep_fn: SleepFn | None = None,
    scancel_fn: ScancelFn | None = None,
    timeout_sec: float = 180.0,
    poll_interval_sec: float = 2.0,
    request_cancel: bool = True,
) -> str | None:
    """
    Ensure an interactive allocation is finished before mutating run-folder state.

    Uses exact job id scancel only (workflow-owned id); polls until terminal.
    """
    jid = (job_id or "").strip()
    if not jid.isdigit():
        return None
    if request_cancel:
        cancel = scancel_fn or scancel_job_local
        cancel(jid)
    return wait_for_slurm_job_terminal(
        jid,
        poll_fn=poll_fn,
        sleep_fn=sleep_fn,
        timeout_sec=timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )
