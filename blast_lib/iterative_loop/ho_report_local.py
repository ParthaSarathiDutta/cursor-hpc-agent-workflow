"""ho.report helpers using local paths only (Perlmutter batch jobs; no SSH/sync)."""

from __future__ import annotations

from pathlib import Path

from blast_lib.metrics import scored_trials, top_k_trials
from blast_lib.parser import parse_ho_report


def count_scored_trials(report_path: Path) -> int:
    trials = parse_ho_report(report_path)
    return len(scored_trials(trials))


def ho_report_path_for_run(run_folder: Path) -> Path:
    return run_folder / "reports" / "ho.report"


def scored_trials_before_cycle(report_path: Path, *, cycle: int) -> int:
    """
    Trials counted before a GPU cycle starts.

    Cycle 1 may start without ho.report (fresh strategy folder) → 0.
    Cycle 2+ requires an existing report (do not reset history silently).
    """
    if not report_path.is_file():
        if cycle == 1:
            return 0
        raise FileNotFoundError(
            f"Missing ho.report at {report_path} before cycle {cycle}. "
            "Report history must exist after cycle 1."
        )
    return count_scored_trials(report_path)


def require_scored_trials_count(report_path: Path) -> int:
    """After a GPU cycle: ho.report must exist and be readable."""
    if not report_path.is_file():
        raise FileNotFoundError(
            f"Missing ho.report at {report_path} after GPU cycle; expected new scored trials."
        )
    return count_scored_trials(report_path)


def history_mode_for_cycle_start(report_path: Path, *, cycle: int) -> str | None:
    """Return 'fresh' | 'continue' for cycle 1 only; else None."""
    if cycle != 1:
        return None
    return "continue" if report_path.is_file() else "fresh"


def best_trial_from_report(report_path: Path) -> dict:
    trials = parse_ho_report(report_path)
    top = top_k_trials(trials, k=1)
    if not top:
        raise ValueError("No scored trials in ho.report")
    return top[0]
