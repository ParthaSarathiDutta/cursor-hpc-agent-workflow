"""Archive regional ho.report history and append global improvement events."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blast_lib.iterative_loop.remote_workflow import agentic_loop_dir, write_json_atomic


def regions_dir(run_folder: Path) -> Path:
    return agentic_loop_dir(run_folder) / "regions"


def region_dir(run_folder: Path, region: int) -> Path:
    return regions_dir(run_folder) / f"region_{region:04d}"


def improvement_events_path(run_folder: Path) -> Path:
    return agentic_loop_dir(run_folder) / "improvement_events.jsonl"


def archive_region_report(
    run_folder: Path,
    *,
    region: int,
    metadata: dict[str, Any],
) -> Path | None:
    """Move active ho.report into region folder; write metadata.json."""
    src = run_folder / "reports" / "ho.report"
    if not src.is_file():
        return None
    dest_dir = region_dir(run_folder, region)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_report = dest_dir / "ho.report"
    shutil.copy2(src, dest_report)
    payload = {
        **metadata,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "ho_report": dest_report.name,
    }
    write_json_atomic(dest_dir / "metadata.json", payload)
    return dest_report


def prepare_fresh_active_report(run_folder: Path) -> None:
    """Remove active ho.report so the next RunBOP starts a fresh regional history."""
    reports = run_folder / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    active = reports / "ho.report"
    if active.is_file():
        active.unlink()


def append_improvement_event(run_folder: Path, event: dict[str, Any]) -> None:
    path = improvement_events_path(run_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({**event, "recorded_at": datetime.now(timezone.utc).isoformat()})
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
