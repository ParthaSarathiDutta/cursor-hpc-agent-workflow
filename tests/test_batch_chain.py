"""Slurm dependency chain construction (no real sbatch)."""

from __future__ import annotations

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.batch_chain import (
    build_cycle_specs,
    parse_sbatch_parsable,
    render_submit_chain_bash,
)
from blast_lib.iterative_loop.remote_workflow import RemoteWorkflow, WorkflowStatus


def test_parse_sbatch_parsable():
    assert parse_sbatch_parsable("12345") == "12345"
    assert parse_sbatch_parsable("12345;perlmutter") == "12345"


def test_build_cycle_specs_dependencies():
    specs = build_cycle_specs(3)
    assert len(specs) == 3
    assert specs[0].gpu_dependency is None
    assert specs[1].gpu_dependency == "afterok:${range1}"
    assert specs[2].gpu_dependency == "afterok:${range2}"


def test_render_chain_three_cycles_afterany_afterok():
    cfg = UIConfig()
    cfg.blast_root = "/global/fake/AgenticBLAST"
    wf = RemoteWorkflow(
        workflow_id="wf-1",
        run_folder="/global/fake/AgenticBLAST/ML-Tersoff-1_PE",
        walltime="04:00:00",
        total_cycles=3,
        status=WorkflowStatus.QUEUED,
    )
    bash = render_submit_chain_bash(cfg, wf)
    assert bash.count("sbatch --parsable") == 6
    assert "--dependency=afterany:$gpu1" in bash
    assert "--dependency=afterany:$gpu2" in bash
    assert "--dependency=afterany:$gpu3" in bash
    assert "--dependency=afterok:${range1}" in bash or "--dependency=afterok:$range1" in bash
    assert "04:00:00" in bash and "WALLTIME=" in bash
    assert "set-gpu-job" in bash and "set-range-job" in bash
    assert bash.count("set-gpu-job") == 3
    assert bash.count("set-range-job") == 3
    assert "TOTAL_CYCLES=3" in bash


def test_render_chain_arbitrary_n_cycles():
    cfg = UIConfig()
    wf = RemoteWorkflow(
        workflow_id="w",
        run_folder="/global/r/R",
        walltime="00:30:00",
        total_cycles=7,
        status=WorkflowStatus.QUEUED,
    )
    bash = render_submit_chain_bash(cfg, wf)
    assert bash.count("sbatch --parsable") == 14
