"""AgenticBLAST must never scancel unrelated NERSC jobs (explicit ids only)."""

from __future__ import annotations

import json

import pytest

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.orchestrator_submit_agent import cancel_orchestrator_workflow
from blast_lib.iterative_loop.slurm_cancel import (
    collect_orchestrator_workflow_cancel_ids,
    scancel_argv,
    validate_slurm_job_id,
)


UNRELATED_GRPO_JOB = "58918906"


def test_validate_slurm_job_id_rejects_broad_cancel_patterns():
    with pytest.raises(ValueError):
        validate_slurm_job_id("--user")
    with pytest.raises(ValueError):
        validate_slurm_job_id("58918906 58918907")
    with pytest.raises(ValueError):
        validate_slurm_job_id("interactive")


def test_collect_orchestrator_ids_from_workflow_json_only():
    wf = {
        "orchestrator_job_id": "111",
        "current_interactive_job_id": "222",
        "cycles": [
            {"cycle": 1, "gpu_job_id": "222", "range_status": None},
            {"cycle": 2, "gpu_job_id": "333", "range_status": "COMPLETED"},
            {"cycle": 3, "gpu_job_id": "999", "range_status": None},
        ],
    }
    assert collect_orchestrator_workflow_cancel_ids(wf) == ["111", "222", "999"]


def test_stop_scancels_only_orchestrator_and_interactive_not_unrelated_job(monkeypatch):
    """
    AgenticBLAST orch=111, interactive=222; unrelated GRPO job 58918906 must never appear in scancel.
    """
    workflow = {
        "workflow_id": "test-wf",
        "orchestrator_job_id": "111",
        "current_interactive_job_id": "222",
        "cycles": [{"cycle": 1, "gpu_job_id": "222", "range_status": None}],
        "status": "RUNNING",
        "phase": "RUNNING_GPU",
    }
    commands: list[str] = []

    def fake_ssh_exec(config, command, timeout=30):
        commands.append(command)
        if command.startswith("cat "):
            return json.dumps(workflow)
        return ""

    monkeypatch.setattr(
        "blast_lib.iterative_loop.orchestrator_submit_agent.ssh_exec",
        fake_ssh_exec,
    )
    monkeypatch.setattr(
        "blast_lib.iterative_loop.orchestrator_submit_agent.ssh_write_file",
        lambda *a, **k: None,
    )

    cfg = UIConfig(blast_root="/global/cfs/cdirs/m4597/partha/AgenticBLAST")
    cancel_orchestrator_workflow(cfg, "/global/cfs/cdirs/m4597/partha/AgenticBLAST/ML-Tersoff-1_PE")

    scancel_cmds = [c for c in commands if "scancel" in c]
    assert scancel_cmds == [
        "scancel 111 2>/dev/null || true",
        "scancel 222 2>/dev/null || true",
    ]
    joined = "\n".join(commands)
    assert UNRELATED_GRPO_JOB not in joined
    assert "scancel -u" not in joined
    assert "gpu_interactive" not in joined


def test_scancel_argv_is_single_numeric_id():
    assert scancel_argv("222") == ["scancel", "222"]
