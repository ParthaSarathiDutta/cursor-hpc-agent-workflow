"""Orchestrator submit rendering (no SSH)."""

from __future__ import annotations

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.orchestrator_submit_agent import render_orchestrator_slurm


def test_render_orchestrator_slurm_cron_qos():
    cfg = UIConfig(
        orchestrator_cron_account="m4597",
        blast_root="/global/cfs/cdirs/m4597/partha/AgenticBLAST",
    )
    body = render_orchestrator_slurm(cfg, log_dir="/run/.agentic_loop/logs", walltime="00:30:00")
    assert "#SBATCH -q cron" in body
    assert "#SBATCH -C cron" in body
    assert "-A m4597" in body
    assert "agentic_loop_orchestrator.py" in body
