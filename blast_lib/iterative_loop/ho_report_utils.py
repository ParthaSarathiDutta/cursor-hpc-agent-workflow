"""ho.report helpers for the iterative loop."""

from __future__ import annotations

from pathlib import Path

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.ho_report_local import best_trial_from_report, count_scored_trials
from blast_lib.remote import sync_run_at_path
from blast_lib.run_catalog import find_report_path


def sync_and_report_path(config: UIConfig, run_folder_path: str) -> Path:
    sync_run_at_path(config, run_folder_path)
    rp = find_report_path(config, run_folder_path)
    if not rp.is_file():
        raise FileNotFoundError(f"No ho.report after sync for {run_folder_path}")
    return rp


__all__ = ["sync_and_report_path", "count_scored_trials", "best_trial_from_report"]
