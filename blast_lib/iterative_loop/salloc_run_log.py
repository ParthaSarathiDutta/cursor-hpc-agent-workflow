"""Persist interactive salloc / Step B combined output for forensics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from blast_lib.iterative_loop.remote_workflow import agentic_loop_dir, write_json_atomic


def salloc_log_path(run_folder: Path, job_id: str | None) -> Path:
    logs = agentic_loop_dir(run_folder) / "logs"
    jid = (job_id or "unknown").strip() or "unknown"
    return logs / f"salloc-{jid}.out"


def _tail(text: str, *, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def persist_salloc_run_output(
    run_folder: Path,
    *,
    job_id: str | None,
    combined_output: str,
    returncode: int | None,
    terminal_slurm_state: str | None,
    aborted: bool = False,
    abort_reason: str | None = None,
) -> Path:
    """Write full combined stdout/stderr; return log path."""
    path = salloc_log_path(run_folder, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# job_id={job_id or ''}\n"
        f"# returncode={returncode}\n"
        f"# terminal_slurm_state={terminal_slurm_state or ''}\n"
        f"# aborted={aborted}\n"
        f"# abort_reason={abort_reason or ''}\n"
        "---\n"
    )
    path.write_text(header + (combined_output or ""), encoding="utf-8")
    return path


def record_allocation_failure_snapshot(
    run_folder: Path,
    *,
    job_id: str | None,
    returncode: int | None,
    terminal_slurm_state: str | None,
    log_path: Path | None,
    combined_output: str,
) -> None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "returncode": returncode,
        "terminal_slurm_state": terminal_slurm_state,
        "log_path": log_path.as_posix() if log_path else None,
        "output_tail": _tail(combined_output or ""),
    }
    write_json_atomic(agentic_loop_dir(run_folder) / "last_allocation_failure.json", payload)
