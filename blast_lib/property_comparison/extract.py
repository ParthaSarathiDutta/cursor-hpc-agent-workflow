"""Load trials and physical blocks from ho.report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from blast_lib.metrics import scored_trials
from blast_lib.parser import parse_ho_report
from blast_lib.property_comparison.config import LATTICE_LABELS, PotentialSpec
from blast_lib.property_comparison.formatting import fmt, fmt_pct, pct_err
from blast_lib.trial_details import extract_target_pred_block


def trial_for_run(run_root: Path) -> dict[str, Any] | None:
    report = run_root / "reports" / "ho.report"
    if not report.is_file():
        return None
    trials = scored_trials(parse_ho_report(report))
    return trials[-1] if trials else None


def input_param_tokens(trial: dict[str, Any] | None) -> list[str]:
    if not trial:
        return []
    raw = (trial.get("input_params") or "").strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1].strip()
    return raw.split()


def elastic_subset(
    trial: dict[str, Any] | None,
    constants: tuple[str, ...],
) -> dict[str, tuple[float | None, float | None]]:
    out: dict[str, tuple[float | None, float | None]] = {k: (None, None) for k in constants}
    if not trial:
        return out
    try:
        block = extract_target_pred_block(trial.get("stage_lines") or [], "elastic")
        idx = {h: i for i, h in enumerate(block["headers"])}
        for name in constants:
            if name not in idx:
                continue
            i = idx[name]
            out[name] = (block["targets"][i], block["predicted"][i])
    except ValueError:
        pass
    return out


def cohesive_pair(trial: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not trial:
        return None, None
    try:
        block = extract_target_pred_block(trial.get("stage_lines") or [], "cohesive")
        return block["targets"][0], block["predicted"][0]
    except ValueError:
        return None, None


def lattice_data(
    snaps: dict[str, dict[str, Any]],
    labels: list[str],
) -> tuple[list[float], dict[str, list[float]]]:
    targets: list[float] = []
    preds: dict[str, list[float]] = {l: [] for l in labels}
    for label in labels:
        trial = snaps[label]["_trial"]
        if not trial:
            continue
        try:
            block = extract_target_pred_block(trial.get("stage_lines") or [], "lattice")
            if not targets:
                targets = block["targets"]
            preds[label] = block["predicted"]
        except ValueError:
            pass
    return targets, preds


def load_snapshots(workspace: Path, potentials: list[PotentialSpec]) -> dict[str, dict[str, Any]]:
    snaps: dict[str, dict[str, Any]] = {}
    for spec in potentials:
        root = workspace / spec.run_dir
        trial = trial_for_run(root)
        snaps[spec.label] = {
            "_trial": trial,
            "_spec": spec,
            "_root": root,
        }
    return snaps
