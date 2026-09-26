#!/usr/bin/env python3
"""GPU cycle entrypoint on Perlmutter (RunBOP + record trial count before)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.iterative_loop.ho_report_local import count_scored_trials  # noqa: E402
from blast_lib.iterative_loop.remote_workflow import (  # noqa: E402
    cycle_before_path,
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


def main() -> int:
    cycle = int(_env("AGENTIC_CYCLE"))
    run_folder = Path(_env("RUN_FOLDER"))
    blast_root = Path(_env("BLAST_ROOT"))
    py = _env("BLAST_PYTHON")
    input_txt = _env("INPUT_TXT")
    workflow_dir = Path(os.environ.get("WORKFLOW_DIR", str(run_folder / ".agentic_loop")))

    rp = run_folder / "reports" / "ho.report"
    if not rp.is_file():
        print(f"ERROR: missing {rp}", file=sys.stderr)
        return 1

    before = count_scored_trials(rp)
    write_json_atomic(
        cycle_before_path(run_folder, cycle),
        {"cycle": cycle, "scored_trials_before": before},
    )

    wf_path = workflow_json_path(run_folder)
    if wf_path.is_file():
        wf = load_workflow(wf_path)
        rec = wf.cycle_record(cycle)
        rec.scored_trials_before = before
        if os.environ.get("SLURM_JOB_ID"):
            rec.gpu_job_id = os.environ["SLURM_JOB_ID"]
        wf.status = "RUNNING"
        wf.status_message = f"GPU cycle {cycle} running (job {rec.gpu_job_id})"
        save_workflow(wf_path, wf)

    shim = blast_root / ".env_shim"
    mpich = "/usr/lib/shifter/mpich-2.2"
    cudart = "/global/cfs/cdirs/m1917/blast_ff/bin/miniconda3/lib/libcudart.so.11.0"
    shim.mkdir(parents=True, exist_ok=True)
    for name, target in [
        ("libcudart.so.11.0", cudart),
        ("libmpi_gnu_91.so.12", f"{mpich}/libmpi_gnu_91.so.12"),
        ("libmpi_gtl_cuda.so.0", f"{mpich}/libmpi_gtl_cuda.so.0"),
    ]:
        link = shim / name
        if target and Path(target).exists():
            if link.is_symlink() or link.exists():
                link.unlink(missing_ok=True)
            link.symlink_to(target)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{shim}:{mpich}:{env.get('LD_LIBRARY_PATH', '')}"

    import shlex

    inner = (
        f'export LD_LIBRARY_PATH="{shim}:{mpich}:$LD_LIBRARY_PATH"; '
        f"cd {{}} && rm -rf tmp && {py} {{}}RunBOP.py"
    )
    cmd = f"cd {blast_root} && cat {input_txt} | parallel -j 1 {shlex.quote(inner)}"
    print(f"Running RunBOP for cycle {cycle}...", flush=True)
    proc = subprocess.run(cmd, shell=True, cwd=str(blast_root), env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
