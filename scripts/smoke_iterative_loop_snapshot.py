#!/usr/bin/env python3
"""Snapshot ho.report / model.json / mcts_restart for smoke test reporting."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blast_lib.agenticblast_submit import normalize_run_path
from blast_lib.config import load_config
from blast_lib.iterative_loop.ho_report_utils import (
    best_trial_from_report,
    count_scored_trials,
    sync_and_report_path,
)
from blast_lib.iterative_loop.range_agent import extract_tersoff_floats, split_mcts_restart_line
from blast_lib.metrics import top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.remote import ssh_read_file


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "BEFORE"
    folder_arg = sys.argv[2] if len(sys.argv) > 2 else "ML-Tersoff-1_PE"
    config = load_config()
    folder = normalize_run_path(config, folder_arg)
    rp = sync_and_report_path(config, folder)
    scored = count_scored_trials(rp)
    best = best_trial_from_report(rp)
    params = extract_tersoff_floats(best.get("input_params", ""))
    model_text = ssh_read_file(config, f"{folder}/model.json")
    restart_text = ssh_read_file(config, f"{folder}/mcts_restart.tersoff")
    prefix, restart_vals = split_mcts_restart_line(restart_text)
    print(f"=== {label} ===")
    print(f"folder: {folder}")
    print(f"scored_trials: {scored}")
    print(f"best_iteration: {best.get('iteration')}")
    print(f"best_score: {best.get('score')}")
    print(f"best_13_params: {params}")
    print(f"mcts_prefix: {prefix!r}")
    print(f"mcts_restart_13: {restart_vals}")
    # sample bounds lines
    for key in ("gamma", "costheta0"):
        for line in model_text.splitlines():
            if f'"{key}"' in line and "[" in line:
                print(f"model.json {key}: {line.strip()}")
                break


if __name__ == "__main__":
    main()
