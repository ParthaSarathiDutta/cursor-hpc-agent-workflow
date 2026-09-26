#!/usr/bin/env python3
"""NERSC cron-QOS driver: sequential interactive salloc + Range cycles."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.iterative_loop.orchestrator_core import (  # noqa: E402
    default_hooks,
    run_orchestrator,
)
from blast_lib.iterative_loop.remote_workflow import (  # noqa: E402
    load_workflow,
    mark_workflow_orchestrator_crash,
    workflow_json_path,
)
from blast_lib.iterative_loop.runbop_launch import (  # noqa: E402
    format_parallel_runbop_command,
    settings_from_workflow,
)


def _step_b_for_workflow(wf) -> str:
    return format_parallel_runbop_command(settings_from_workflow(wf))


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

    try:
        wf = load_workflow(wf_path)
        step_b = _step_b_for_workflow(wf)
        hooks = default_hooks()
        return run_orchestrator(wf_path, step_b=step_b, hooks=hooks)
    except Exception as exc:  # noqa: BLE001 — top-level guard for cron job
        mark_workflow_orchestrator_crash(wf_path, exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
