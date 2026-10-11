"""ho.report helpers using local paths only (Perlmutter batch jobs; no SSH/sync)."""

from __future__ import annotations

from pathlib import Path

from blast_lib.metrics import scored_trials, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.trial_details import parse_property_blocks

NO_ELASTIC_CANDIDATE = "NO_ELASTIC_CANDIDATE"


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


def elastic_values_obj_from_trial(trial: dict) -> float | None:
    blocks = [
        b
        for b in parse_property_blocks(trial.get("stage_lines") or [])
        if b.get("stage") == "elastic" and not b.get("missing")
    ]
    if not blocks:
        return None
    raw = (blocks[-1].get("metrics") or {}).get("values.obj")
    if raw is None:
        return None
    return float(raw)


def elastic_eligible_trials(report_path: Path) -> list[dict]:
    trials = scored_trials(parse_ho_report(report_path))
    out: list[dict] = []
    for trial in trials:
        obj = elastic_values_obj_from_trial(trial)
        if obj is not None:
            out.append({**trial, "_elastic_values_obj": obj})
    return out


def count_elastic_eligible_trials(report_path: Path) -> int:
    return len(elastic_eligible_trials(report_path))


def best_elastic_trial_from_report(report_path: Path) -> dict:
    eligible = elastic_eligible_trials(report_path)
    if not eligible:
        raise ValueError(NO_ELASTIC_CANDIDATE)
    return min(eligible, key=lambda t: t["_elastic_values_obj"])


def select_trial_for_range(report_path: Path, *, strategy: str) -> dict:
    if strategy == "elastic":
        return best_elastic_trial_from_report(report_path)
    return best_trial_from_report(report_path)
