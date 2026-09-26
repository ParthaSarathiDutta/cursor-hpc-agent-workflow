"""Build interactive salloc + Step B shell (no full UIConfig required on NERSC)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class SallocSettings:
    blast_root: str
    walltime: str
    account: str
    nodes: int = 2
    ntasks_per_node: int = 4
    gpus_per_task: int = 1
    gpus: int = 8
    qos: str = "interactive"


def format_salloc_fragment(settings: SallocSettings) -> str:
    return " ".join(
        [
            "salloc",
            f"--nodes {settings.nodes}",
            f"--qos {settings.qos}",
            f"--time {settings.walltime}",
            f"--ntasks-per-node={settings.ntasks_per_node}",
            "--constraint gpu",
            f"--gpus-per-task={settings.gpus_per_task}",
            f"--gpus {settings.gpus}",
            "--gpu-bind=none",
            f"--account {settings.account}",
        ]
    )


def build_interactive_runbop_shell(
    settings: SallocSettings,
    *,
    step_b: str,
) -> str:
    """cd blast_root && salloc ... -- bash -c 'step_b' (Step B on compute nodes)."""
    root = settings.blast_root.rstrip("/")
    inner = step_b.strip()
    if not inner:
        raise ValueError("Step B command is empty.")
    escaped = inner.replace("'", "'\\''")
    salloc = format_salloc_fragment(settings)
    return f"cd {shlex.quote(root)} && {salloc} -- bash -c '{escaped}'"
