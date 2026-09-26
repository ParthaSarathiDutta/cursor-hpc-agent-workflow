"""ho.report helpers using local paths only (Perlmutter batch jobs; no SSH/sync)."""

from __future__ import annotations

from pathlib import Path

from blast_lib.metrics import scored_trials, top_k_trials
from blast_lib.parser import parse_ho_report


def count_scored_trials(report_path: Path) -> int:
    trials = parse_ho_report(report_path)
    return len(scored_trials(trials))


def best_trial_from_report(report_path: Path) -> dict:
    trials = parse_ho_report(report_path)
    top = top_k_trials(trials, k=1)
    if not top:
        raise ValueError("No scored trials in ho.report")
    return top[0]
