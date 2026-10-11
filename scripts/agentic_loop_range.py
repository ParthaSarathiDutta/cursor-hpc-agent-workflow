#!/usr/bin/env python3
"""Range cycle entrypoint on Perlmutter (local, no SSH)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.iterative_loop.ho_report_local import count_scored_trials  # noqa: E402
from blast_lib.iterative_loop.range_core import run_range_update_local  # noqa: E402
from blast_lib.iterative_loop.remote_workflow import (  # noqa: E402
    WorkflowStatus,
    cycle_before_path,
    cycle_range_result_path,
    load_workflow,
    save_workflow,
    workflow_json_path,
    write_json_atomic,
)


def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"Missing env {name}")
    return val


def _mark_failed(run_folder: Path, cycle: int, message: str) -> None:
    wf_path = workflow_json_path(run_folder)
    if not wf_path.is_file():
        return
    wf = load_workflow(wf_path)
    rec = wf.cycle_record(cycle)
    rec.range_status = "FAILED"
    rec.error = message
    if os.environ.get("SLURM_JOB_ID"):
        rec.range_job_id = os.environ["SLURM_JOB_ID"]
    wf.status = WorkflowStatus.FAILED
    wf.error = message
    wf.status_message = f"Range cycle {cycle} failed."
    save_workflow(wf_path, wf)


def main() -> int:
    cycle = int(_env("AGENTIC_CYCLE"))
    gpu_job_id = _env("GPU_JOB_ID")
    run_folder = Path(_env("RUN_FOLDER"))
    py = _env("BLAST_PYTHON")
    walltime = _env("WALLTIME")
    total_cycles = int(_env("TOTAL_CYCLES"))

    before_path = cycle_before_path(run_folder, cycle)
    if not before_path.is_file():
        msg = f"Missing {before_path} (GPU cycle may not have recorded trial baseline)."
        _mark_failed(run_folder, cycle, msg)
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    before = int(json.loads(before_path.read_text())["scored_trials_before"])

    result = run_range_update_local(
        run_folder,
        py,
        scored_before=before,
        gpu_job_id=gpu_job_id,
        walltime=walltime,
    )

    after = count_scored_trials(run_folder / "reports" / "ho.report")
    write_json_atomic(
        cycle_range_result_path(run_folder, cycle),
        {
            "cycle": cycle,
            "ok": result.ok,
            "message": result.message,
            "scored_trials_after": after,
            "best_score": result.best_score,
            "best_iteration": result.best_iteration,
            "gpu_elapsed_sec": result.gpu_elapsed_sec,
        },
    )

    wf_path = workflow_json_path(run_folder)
    if wf_path.is_file():
        wf = load_workflow(wf_path)
        rec = wf.cycle_record(cycle)
        rec.scored_trials_after = after
        rec.best_score = result.best_score
        rec.best_iteration = result.best_iteration
        rec.last_slurm_elapsed_sec = result.gpu_elapsed_sec
        if os.environ.get("SLURM_JOB_ID"):
            rec.range_job_id = os.environ["SLURM_JOB_ID"]
        if result.ok:
            rec.range_status = "COMPLETED"
            wf.error = None
            wf.status_message = f"Range cycle {cycle} completed."
            if cycle >= total_cycles:
                wf.status = WorkflowStatus.COMPLETED
                wf.status_message = f"Workflow complete — {total_cycles} cycle(s) finished."
            else:
                wf.status = WorkflowStatus.RUNNING
        else:
            rec.range_status = "FAILED"
            rec.error = result.message
            wf.status = WorkflowStatus.FAILED
            wf.error = result.message
            wf.status_message = f"Range cycle {cycle} failed."
        save_workflow(wf_path, wf)

    if not result.ok:
        print(result.message, file=sys.stderr)
        return 1
    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
