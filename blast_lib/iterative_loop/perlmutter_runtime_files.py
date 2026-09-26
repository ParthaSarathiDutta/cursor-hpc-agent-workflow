"""Paths under repo root required on Perlmutter for GPU/Range batch jobs (no SSH at runtime)."""

from __future__ import annotations

from blast_lib.config_types import REPO_ROOT

PERLMUTTER_RUNTIME_REL_PATHS: tuple[str, ...] = (
    "blast_lib/__init__.py",
    "blast_lib/parser.py",
    "blast_lib/metrics.py",
    "blast_lib/changemodel_bounds.py",
    "blast_lib/config_types.py",
    "blast_lib/iterative_loop/__init__.py",
    "blast_lib/iterative_loop/ho_report_local.py",
    "blast_lib/iterative_loop/tersoff_params.py",
    "blast_lib/iterative_loop/range_types.py",
    "blast_lib/iterative_loop/range_core.py",
    "blast_lib/iterative_loop/remote_workflow.py",
    "blast_lib/iterative_loop/slurm_timing.py",
    "scripts/agentic_loop_gpu.py",
    "scripts/agentic_loop_range.py",
    "scripts/agentic_loop_workflow_cli.py",
)


def iter_runtime_files():
    for rel in PERLMUTTER_RUNTIME_REL_PATHS:
        path = REPO_ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"Missing Perlmutter runtime file: {rel}")
        yield rel, path
