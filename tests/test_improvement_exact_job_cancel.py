"""Improvement path uses the same exact-job scancel as Stop (stream_shell_run)."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.iterative_loop.orchestrator_core import stream_shell_run


def test_improvement_abort_path_scancels_exact_job(monkeypatch, tmp_path: Path):
    cancelled: list[str] = []
    monkeypatch.setattr(
        "blast_lib.iterative_loop.orchestrator_core.scancel_job_local",
        lambda jid: cancelled.append(jid),
    )
    abort_state: dict = {"reason": None, "trigger": None}
    polls = {"n": 0}

    def should_abort():
        polls["n"] += 1
        if polls["n"] >= 2:
            abort_state["reason"] = "improvement"
            return True
        return False

    script = "echo 'Granted job allocation 424242'; exec sleep 9999"
    result = stream_shell_run(
        script,
        {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        should_abort=should_abort,
        abort_state=abort_state,
        poll_slurm_job_state=lambda _: "RUNNING",
        poll_interval_sec=0.05,
        cleanup_grace_sec=1.0,
        cleanup_kill_timeout_sec=5.0,
    )
    assert result.job_id == "424242"
    assert cancelled == ["424242"]
    assert result.abort_reason == "improvement"
