"""Range update on Perlmutter filesystem (no SSH)."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from blast_lib.iterative_loop.ho_report_local import (
    NO_ELASTIC_CANDIDATE,
    count_elastic_eligible_trials,
    count_scored_trials,
    elastic_values_obj_from_trial,
    select_trial_for_range,
)
from blast_lib.iterative_loop.selection_strategy import STRATEGY_ELASTIC, load_selection_strategy
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


def apply_recenter_from_trial(
    run_folder: Path,
    blast_python: str,
    trial: dict,
    *,
    selection_strategy: str,
    selection_reason: str | None = None,
    gpu_elapsed_sec: int | None = None,
) -> RangeUpdateResult:
    """Shared ±10% changemodel + mcts_restart update from an explicit trial (RangeAgent path)."""
    run_folder = run_folder.resolve()
    try:
        input_params = trial.get("input_params") or ""
        elastic_obj = elastic_values_obj_from_trial(trial)
        if selection_reason is None:
            if selection_strategy == STRATEGY_ELASTIC:
                reason = "elastic.values.obj improvement"
            else:
                reason = "minimum finalObj"
        else:
            reason = selection_reason

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
            gpu_elapsed_sec=gpu_elapsed_sec,
            selection_strategy=selection_strategy,
            selection_reason=reason,
            elastic_values_obj=elastic_obj,
        )
    except ValueError as exc:
        return RangeUpdateResult(
            ok=False,
            message=str(exc),
            selection_strategy=selection_strategy,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RangeUpdateResult(ok=False, message=str(exc), selection_strategy=selection_strategy)


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
        return RangeUpdateResult(
            ok=False,
            message=(
                f"Missing ho.report at {rp} after GPU cycle; "
                "expected RunBOP to create reports/ho.report with scored trials."
            ),
        )

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

    strategy = load_selection_strategy(run_folder)
    if strategy == STRATEGY_ELASTIC and count_elastic_eligible_trials(rp) == 0:
        return RangeUpdateResult(
            ok=False,
            message=(
                f"{NO_ELASTIC_CANDIDATE}: no elastic-reaching trials with values.obj "
                f"in {rp} (2-minute sample may be too short)."
            ),
            selection_strategy=strategy,
            selection_reason=NO_ELASTIC_CANDIDATE,
        )

    try:
        trial = select_trial_for_range(rp, strategy=strategy)
        if strategy == STRATEGY_ELASTIC:
            reason = "minimum elastic.values.obj"
        else:
            reason = "minimum finalObj"
        result = apply_recenter_from_trial(
            run_folder,
            blast_python,
            trial,
            selection_strategy=strategy,
            selection_reason=reason,
            gpu_elapsed_sec=elapsed,
        )
        return result
    except ValueError as exc:
        if str(exc) == NO_ELASTIC_CANDIDATE:
            return RangeUpdateResult(
                ok=False,
                message=f"{NO_ELASTIC_CANDIDATE}: no elastic candidate in {rp}",
                selection_strategy=strategy,
                selection_reason=NO_ELASTIC_CANDIDATE,
            )
        return RangeUpdateResult(ok=False, message=str(exc), selection_strategy=strategy)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RangeUpdateResult(ok=False, message=str(exc), selection_strategy=strategy)
