"""Orchestrator crash must mark workflow.json FAILED."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.iterative_loop.remote_workflow import (
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    load_workflow,
    mark_workflow_orchestrator_crash,
    save_workflow,
    workflow_json_path,
)


def test_orchestrator_crash_marks_failed(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    path = workflow_json_path(run)
    wf = RemoteWorkflow(
        workflow_id="w",
        run_folder=str(run),
        walltime="00:02:00",
        total_cycles=1,
        status=WorkflowStatus.RUNNING,
        phase=WorkflowPhase.AWAITING_SALLOC,
    )
    save_workflow(path, wf)
    mark_workflow_orchestrator_crash(path, RuntimeError("ModuleNotFoundError: blast_lib.remote"))
    loaded = load_workflow(path)
    assert loaded.status == WorkflowStatus.FAILED
    assert loaded.phase == WorkflowPhase.FAILED
    assert "remote" in (loaded.error or "")


def test_orchestrator_crash_does_not_overwrite_stopped(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    path = workflow_json_path(run)
    wf = RemoteWorkflow(
        workflow_id="w",
        run_folder=str(run),
        walltime="00:02:00",
        total_cycles=1,
        status=WorkflowStatus.STOPPED,
        phase=WorkflowPhase.STOPPED,
        status_message="User stop",
    )
    save_workflow(path, wf)
    mark_workflow_orchestrator_crash(path, RuntimeError("should not apply"))
    loaded = load_workflow(path)
    assert loaded.status == WorkflowStatus.STOPPED
    assert loaded.status_message == "User stop"


def test_orchestrator_main_exception_marks_failed(tmp_path: Path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    path = workflow_json_path(run)
    wf = RemoteWorkflow(
        workflow_id="w",
        run_folder=str(run),
        walltime="00:02:00",
        total_cycles=1,
        status=WorkflowStatus.RUNNING,
        phase=WorkflowPhase.AWAITING_SALLOC,
        blast_root="/blast",
        blast_python="/usr/bin/python",
    )
    save_workflow(path, wf)

    import scripts.agentic_loop_orchestrator as orch

    def boom(*args, **kwargs):
        raise ValueError("simulated orchestrator fault")

    monkeypatch.setattr(orch, "run_orchestrator", boom)
    rc = orch.main([str(run)])
    assert rc == 1
    loaded = load_workflow(path)
    assert loaded.status == WorkflowStatus.FAILED
    assert "simulated" in (loaded.error or "")
