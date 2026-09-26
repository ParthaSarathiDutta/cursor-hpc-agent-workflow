#!/usr/bin/env python3
"""NERSC cron-QOS driver: sequential interactive salloc + Range cycles."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.agenticblast_submit import format_parallel_command  # noqa: E402
from blast_lib.config_types import UIConfig  # noqa: E402
from blast_lib.iterative_loop.orchestrator_core import (  # noqa: E402
    default_hooks,
    run_orchestrator,
)
from blast_lib.iterative_loop.remote_workflow import workflow_json_path  # noqa: E402


def _step_b_for_workflow(wf) -> str:
    cfg = UIConfig(
        blast_root=wf.blast_root,
        blast_python=wf.blast_python,
        submit_account=wf.gpu_account or wf.salloc_account,
        salloc_nodes=wf.salloc_nodes,
        salloc_ntasks_per_node=wf.salloc_ntasks_per_node,
        salloc_gpus_per_task=wf.salloc_gpus_per_task,
        salloc_gpus=wf.salloc_gpus,
    )
    return format_parallel_command(cfg)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: agentic_loop_orchestrator.py <run_folder>", file=sys.stderr)
        return 2
    run_folder = args[0]
    wf_path = workflow_json_path(run_folder)
    if not wf_path.is_file():
        print(f"Missing {wf_path}", file=sys.stderr)
        return 1
    from blast_lib.iterative_loop.remote_workflow import load_workflow

    wf = load_workflow(wf_path)
    step_b = _step_b_for_workflow(wf)
    hooks = default_hooks()
    return run_orchestrator(wf_path, step_b=step_b, hooks=hooks)


if __name__ == "__main__":
    raise SystemExit(main())
