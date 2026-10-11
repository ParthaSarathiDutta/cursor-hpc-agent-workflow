"""NERSC workflow.json persistence."""

from __future__ import annotations

from pathlib import Path

from blast_lib.iterative_loop.remote_workflow import (
    CycleRecord,
    RemoteWorkflow,
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)


def test_atomic_save_load_roundtrip(tmp_path: Path):
    run = tmp_path / "ML-Tersoff-1_PE"
    run.mkdir()
    path = workflow_json_path(run)
    wf = RemoteWorkflow(
        workflow_id="abc",
        run_folder=str(run),
        walltime="02:00:00",
        total_cycles=2,
        status=WorkflowStatus.RUNNING,
        cycles=[CycleRecord(cycle=1, gpu_job_id="111")],
    )
    save_workflow(path, wf)
    loaded = load_workflow(path)
    assert loaded.workflow_id == "abc"
    assert loaded.cycles[0].gpu_job_id == "111"


def test_completed_status_field(tmp_path: Path):
    path = tmp_path / "workflow.json"
    wf = RemoteWorkflow(
        workflow_id="x",
        run_folder="/fake",
        walltime="01:00:00",
        total_cycles=1,
        status=WorkflowStatus.COMPLETED,
    )
    save_workflow(path, wf)
    assert load_workflow(path).status == WorkflowStatus.COMPLETED
