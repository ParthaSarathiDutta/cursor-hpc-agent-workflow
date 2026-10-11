"""Hierarchy epoch archives and observation-window event log."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blast_lib.iterative_loop.remote_workflow import agentic_loop_dir, write_json_atomic


def hierarchy_epochs_dir(run_folder: Path) -> Path:
    return agentic_loop_dir(run_folder) / "hierarchy_epochs"


def hierarchy_epoch_dir(run_folder: Path, epoch: int) -> Path:
    return hierarchy_epochs_dir(run_folder) / f"epoch_{epoch:04d}"


def hierarchy_events_path(run_folder: Path) -> Path:
    return agentic_loop_dir(run_folder) / "hierarchy_events.jsonl"


def archive_hierarchy_epoch_report(
    run_folder: Path,
    *,
    epoch: int,
    metadata: dict[str, Any],
) -> Path | None:
    src = run_folder / "reports" / "ho.report"
    if not src.is_file():
        return None
    dest_dir = hierarchy_epoch_dir(run_folder, epoch)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_report = dest_dir / "ho.report"
    shutil.copy2(src, dest_report)
    payload = {
        **metadata,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "hierarchy_epoch": epoch,
        "ho_report": dest_report.name,
    }
    write_json_atomic(dest_dir / "metadata.json", payload)
    return dest_report


def archive_mcts_tree_if_present(run_folder: Path, *, epoch: int) -> list[str]:
    archived: list[str] = []
    dest_dir = hierarchy_epoch_dir(run_folder, epoch)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in ("mctree.restart", "finaltree.restart"):
        src = run_folder / name
        if src.is_file():
            dest = dest_dir / name
            shutil.copy2(src, dest)
            archived.append(name)
    return archived


def reset_mcts_tree_files(run_folder: Path) -> list[str]:
    removed: list[str] = []
    for name in ("mctree.restart", "finaltree.restart"):
        path = run_folder / name
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


def prepare_fresh_active_report(run_folder: Path) -> None:
    reports = run_folder / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    active = reports / "ho.report"
    if active.is_file():
        active.unlink()


def append_hierarchy_event(run_folder: Path, event: dict[str, Any]) -> None:
    path = hierarchy_events_path(run_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({**event, "recorded_at": datetime.now(timezone.utc).isoformat()})
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
