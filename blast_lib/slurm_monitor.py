"""Poll Slurm job state on Perlmutter via SSH."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from blast_lib.config_types import UIConfig
from blast_lib.remote import RemoteError, ssh_exec


@dataclass
class SlurmJobStatus:
    job_id: str
    active: bool
    queue_state: str | None = None
    sacct_state: str | None = None


def query_job_status(config: UIConfig, job_id: str) -> SlurmJobStatus:
    jid = shlex.quote(job_id)
    try:
        queue = ssh_exec(
            config,
            f"squeue -j {jid} -h -o '%T' 2>/dev/null || true",
            timeout=25,
        ).strip()
    except RemoteError:
        queue = ""

    if queue:
        return SlurmJobStatus(job_id=job_id, active=True, queue_state=queue.splitlines()[0])

    try:
        sacct = ssh_exec(
            config,
            f"sacct -j {jid} --format=State -P -n 2>/dev/null | head -1 || true",
            timeout=25,
        ).strip()
    except RemoteError:
        sacct = ""

    state = sacct.split("|")[0].strip() if sacct else None
    return SlurmJobStatus(job_id=job_id, active=False, sacct_state=state or None)
