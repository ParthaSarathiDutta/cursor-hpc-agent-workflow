"""Range update on Perlmutter filesystem (no SSH)."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from blast_lib.iterative_loop.ho_report_local import best_trial_from_report, count_scored_trials
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.iterative_loop.tersoff_params import (
    DEFAULT_SB_PREFIX,
    extract_tersoff_param_strings,
    format_mcts_restart_line,
    split_mcts_restart_line,
)
from blast_lib.iterative_loop.slurm_timing import allocation_met_walltime, fetch_job_elapsed_seconds_local


def ho_report_path(run_folder: Path) -> Path:
    return run_folder / "reports" / "ho.report"


def run_range_update_local(
    run_folder: Path,
    blast_python: str,
    *,
    scored_before: int,
    gpu_job_id: str,
    walltime: str,
) -> RangeUpdateResult:
    run_folder = run_folder.resolve()
    rp = ho_report_path(run_folder)
    if not rp.is_file():
        return RangeUpdateResult(ok=False, message=f"Missing ho.report at {rp}")

    elapsed = fetch_job_elapsed_seconds_local(gpu_job_id)
    if elapsed is None:
        return RangeUpdateResult(
            ok=False,
            message=f"Could not read sacct Elapsed for GPU job {gpu_job_id}",
        )
    met, required_sec = allocation_met_walltime(elapsed, walltime)
    if not met:
        return RangeUpdateResult(
            ok=False,
            message=(
                f"Allocation too short: sacct elapsed {elapsed}s "
                f"(need ≥{required_sec}s walltime {walltime}, 5s slack)."
            ),
        )

    after = count_scored_trials(rp)
    if after <= scored_before:
        return RangeUpdateResult(
            ok=False,
            message=f"No new scored trials (before={scored_before}, after={after}).",
        )

    try:
        trial = best_trial_from_report(rp)
        input_params = trial.get("input_params") or ""
        param_strings = extract_tersoff_param_strings(input_params)
        param_floats = [float(x) for x in param_strings]

        args = " ".join(shlex.quote(s) for s in param_strings)
        cmd = f"{shlex.quote(blast_python)} changemodel.json.py {args}"
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(run_folder),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            return RangeUpdateResult(ok=False, message=f"changemodel.json.py failed: {err}")

        restart_path = run_folder / "mcts_restart.tersoff"
        if restart_path.is_file():
            prefix, _ = split_mcts_restart_line(restart_path.read_text())
        else:
            prefix = DEFAULT_SB_PREFIX
        restart_path.write_text(format_mcts_restart_line(prefix, param_floats))

        msg = (proc.stdout or "changemodel.json.py completed").strip()
        return RangeUpdateResult(
            ok=True,
            message=msg,
            best_score=trial.get("score"),
            best_iteration=trial.get("iteration"),
            gpu_elapsed_sec=elapsed,
        )
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return RangeUpdateResult(ok=False, message=str(exc))
