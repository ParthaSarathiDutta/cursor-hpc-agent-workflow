"""Range entrypoint must mark workflow FAILED before non-zero exit."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from blast_lib.iterative_loop.remote_workflow import WorkflowStatus, load_workflow, save_workflow, workflow_json_path


def test_mark_failed_on_missing_before(tmp_path: Path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    wf_path = workflow_json_path(run)
    from blast_lib.iterative_loop.remote_workflow import RemoteWorkflow

    save_workflow(
        wf_path,
        RemoteWorkflow(
            workflow_id="t",
            run_folder=str(run),
            walltime="04:00:00",
            total_cycles=1,
            status=WorkflowStatus.RUNNING,
        ),
    )

    monkeypatch.setenv("AGENTIC_CYCLE", "1")
    monkeypatch.setenv("GPU_JOB_ID", "12345")
    monkeypatch.setenv("RUN_FOLDER", str(run))
    monkeypatch.setenv("BLAST_PYTHON", "python")
    monkeypatch.setenv("WALLTIME", "04:00:00")
    monkeypatch.setenv("TOTAL_CYCLES", "1")
    monkeypatch.setenv("SLURM_JOB_ID", "99999")

    from scripts import agentic_loop_range as mod

    code = mod.main()
    assert code == 1
    wf = load_workflow(wf_path)
    assert wf.status == WorkflowStatus.FAILED
    assert wf.error
