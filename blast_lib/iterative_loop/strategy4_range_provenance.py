"""Append-only provenance for Strategy 4 overall Range after productive GPU allocations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blast_lib.iterative_loop.remote_workflow import agentic_loop_dir
from blast_lib.iterative_loop.range_types import RangeUpdateResult


def strategy4_range_events_path(run_folder: Path) -> Path:
    return agentic_loop_dir(run_folder) / "strategy4_range_events.jsonl"


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _optional_selected_vector(run_folder: Path, range_result: RangeUpdateResult) -> list[float] | None:
    if not range_result.ok or range_result.best_iteration is None:
        return None
    try:
        from blast_lib.iterative_loop.ho_report_local import select_trial_for_range
        from blast_lib.iterative_loop.selection_strategy import STRATEGY_OVERALL
        from blast_lib.iterative_loop.tersoff_params import extract_tersoff_param_strings

        rp = run_folder / "reports" / "ho.report"
        if not rp.is_file():
            return None
        trial = select_trial_for_range(rp, strategy=STRATEGY_OVERALL)
        if trial.get("iteration") != range_result.best_iteration:
            return None
        input_params = trial.get("input_params") or ""
        if not input_params:
            return None
        return [float(x) for x in extract_tersoff_param_strings(input_params)]
    except (ValueError, OSError, TypeError):
        return None


def _json_safe_range_fields(range_result: RangeUpdateResult) -> dict[str, Any]:
    if not isinstance(range_result, RangeUpdateResult):
        return {
            "ok": False,
            "message": "invalid range result type",
            "selection_strategy": None,
            "selection_reason": None,
            "best_iteration": None,
            "best_score": None,
            "gpu_elapsed_sec": None,
        }

    def _opt_int(val: object) -> int | None:
        if val is None:
            return None
        try:
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _opt_float(val: object) -> float | None:
        if val is None:
            return None
        try:
            return float(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    return {
        "ok": bool(range_result.ok),
        "message": str(range_result.message or ""),
        "selection_strategy": range_result.selection_strategy,
        "selection_reason": range_result.selection_reason,
        "best_iteration": _opt_int(range_result.best_iteration),
        "best_score": _opt_float(range_result.best_score),
        "gpu_elapsed_sec": _opt_int(range_result.gpu_elapsed_sec),
    }


def append_strategy4_range_event(run_folder: Path, event: dict[str, Any]) -> None:
    path = strategy4_range_events_path(run_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**event, "recorded_at": datetime.now(timezone.utc).isoformat()}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def record_strategy4_range_outcome(
    run_folder: Path,
    *,
    workflow_id: str,
    gpu_job_id: str,
    hierarchy_epoch: int,
    active_hierarchy: list[str],
    range_result: RangeUpdateResult,
    model_json_sha256_before: str,
    model_json_sha256_after: str,
    mcts_restart_sha256_before: str,
    mcts_restart_sha256_after: str,
) -> None:
    """Log one Range attempt (success or failure); does not affect Range selection."""
    fields = _json_safe_range_fields(range_result)
    vector = _optional_selected_vector(run_folder, range_result) if fields["ok"] else None
    event: dict[str, Any] = {
        "event_type": "strategy4_range",
        "workflow_id": workflow_id,
        "gpu_job_id": gpu_job_id,
        "hierarchy_epoch": hierarchy_epoch,
        "active_hierarchy": list(active_hierarchy),
        **fields,
        "model_json_sha256_before": model_json_sha256_before,
        "model_json_sha256_after": model_json_sha256_after,
        "mcts_restart_sha256_before": mcts_restart_sha256_before,
        "mcts_restart_sha256_after": mcts_restart_sha256_after,
    }
    if vector is not None:
        event["selected_param_vector"] = vector
    append_strategy4_range_event(run_folder, event)
