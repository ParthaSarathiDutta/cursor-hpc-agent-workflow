#!/usr/bin/env python3
"""CLI for workflow.json updates on Perlmutter (atomic; no SSH)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.iterative_loop.remote_workflow import (  # noqa: E402
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)


def cmd_set_gpu_job(run_folder: str, cycle: int, job_id: str) -> int:
    path = workflow_json_path(run_folder)
    wf = load_workflow(path)
    rec = wf.cycle_record(cycle)
    rec.gpu_job_id = job_id.strip()
    wf.status = WorkflowStatus.RUNNING
    wf.status_message = f"GPU cycle {cycle} submitted (job {job_id})."
    save_workflow(path, wf)
    return 0


def cmd_set_range_job(run_folder: str, cycle: int, job_id: str) -> int:
    path = workflow_json_path(run_folder)
    wf = load_workflow(path)
    rec = wf.cycle_record(cycle)
    rec.range_job_id = job_id.strip()
    wf.status_message = f"Range cycle {cycle} submitted (job {job_id})."
    save_workflow(path, wf)
    return 0


def cmd_mark_running(run_folder: str, message: str) -> int:
    path = workflow_json_path(run_folder)
    wf = load_workflow(path)
    wf.status = WorkflowStatus.RUNNING
    wf.status_message = message
    save_workflow(path, wf)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Update .agentic_loop/workflow.json on NERSC")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gpu = sub.add_parser("set-gpu-job")
    p_gpu.add_argument("run_folder")
    p_gpu.add_argument("cycle", type=int)
    p_gpu.add_argument("job_id")

    p_rng = sub.add_parser("set-range-job")
    p_rng.add_argument("run_folder")
    p_rng.add_argument("cycle", type=int)
    p_rng.add_argument("job_id")

    p_run = sub.add_parser("mark-running")
    p_run.add_argument("run_folder")
    p_run.add_argument("message")

    args = parser.parse_args()
    if args.cmd == "set-gpu-job":
        return cmd_set_gpu_job(args.run_folder, args.cycle, args.job_id)
    if args.cmd == "set-range-job":
        return cmd_set_range_job(args.run_folder, args.cycle, args.job_id)
    if args.cmd == "mark-running":
        return cmd_mark_running(args.run_folder, args.message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
