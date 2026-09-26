"""Orchestrator sequential cycle logic (no real Slurm)."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.iterative_loop.orchestrator_core import (
    OrchestratorHooks,
    SallocRunResult,
    build_interactive_runbop_shell,
    clear_inherited_slurm_env,
    estimate_orchestrator_cron_walltime,
    run_orchestrator,
    salloc_settings_from_workflow,
    walltime_hms_to_seconds,
)
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.iterative_loop.remote_workflow import (
    CycleRecord,
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)
from blast_lib.iterative_loop.salloc_command import SallocSettings


def _wf(tmp_path: Path, *, cycles: int = 2) -> RemoteWorkflow:
    run = tmp_path / "run"
    run.mkdir()
    (run / "reports").mkdir()
    (run / "reports" / "ho.report").write_text("dummy\n")
    return RemoteWorkflow(
        workflow_id="w1",
        run_folder=str(run),
        walltime="00:02:00",
        total_cycles=cycles,
        status=WorkflowStatus.QUEUED,
        phase=WorkflowPhase.QUEUED,
        blast_root="/blast",
        blast_python="/usr/bin/python",
        gpu_account="m4597_g",
        salloc_nodes=2,
        salloc_gpus=8,
    )


def test_clear_inherited_slurm_env():
    env = {"PATH": "/bin", "SLURM_JOB_ID": "1", "SLURM_MEM_PER_CPU": "2048"}
    cleaned = clear_inherited_slurm_env(env)
    assert "SLURM_JOB_ID" not in cleaned
    assert cleaned["PATH"] == "/bin"


def test_walltime_propagates_to_salloc_command(tmp_path: Path):
    wf = _wf(tmp_path)
    wf.walltime = "00:10:00"
    settings = salloc_settings_from_workflow(wf)
    cmd = build_interactive_runbop_shell(settings, step_b="echo hi")
    assert "--time 00:10:00" in cmd
    assert "--qos interactive" in cmd
    assert "--account m4597_g" in cmd


def test_estimate_cron_walltime_two_cycles():
    t = estimate_orchestrator_cron_walltime(total_cycles=2, cycle_walltime="00:02:00", margin_hours=1.0)
    assert walltime_hms_to_seconds(t) >= 2 * 120


@pytest.fixture
def orchestrator_harness(tmp_path: Path):
    wf = _wf(tmp_path, cycles=2)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    salloc_calls: list[str] = []
    range_calls: list[int] = []
    trials = {"n": 10}

    def run_shell(cmd: str, env: dict) -> SallocRunResult:
        assert not any(k.startswith("SLURM_") for k in env)
        salloc_calls.append(cmd)
        return SallocRunResult(
            returncode=0,
            combined_output="Granted job allocation 90001",
            job_id="90001",
        )

    def run_range(rf, py, before, jid, wt):
        range_calls.append(before)
        trials["n"] += 5
        return RangeUpdateResult(
            ok=True,
            message="ok",
            best_score=1.0,
            best_iteration=3,
            gpu_elapsed_sec=120,
        )

    def count_trials(rp):
        return trials["n"]

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=run_range,
        count_trials=count_trials,
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={"SLURM_JOB_ID": "cron1", "PATH": "/bin"},
        salloc_retry_sleep_sec=0,
    )
    return path, hooks, salloc_calls, range_calls


def test_n_cycles_sequential_salloc_and_range(orchestrator_harness):
    path, hooks, salloc_calls, range_calls = orchestrator_harness
    rc = run_orchestrator(path, step_b="echo stepb", hooks=hooks)
    assert rc == 0
    assert len(salloc_calls) == 2
    assert len(range_calls) == 2
    final = load_workflow(path)
    assert final.status == WorkflowStatus.COMPLETED
    assert final.phase == WorkflowPhase.COMPLETED
    assert final.cycles[0].range_status == "COMPLETED"
    assert final.cycles[1].range_status == "COMPLETED"


def test_range_failure_stops_before_second_salloc(orchestrator_harness):
    path, hooks, salloc_calls, range_calls = orchestrator_harness
    calls = {"n": 0}

    def fail_range(*args, **kwargs):
        calls["n"] += 1
        return RangeUpdateResult(ok=False, message="range broke")

    hooks.run_range = fail_range
    rc = run_orchestrator(path, step_b="echo stepb", hooks=hooks)
    assert rc == 1
    assert len(salloc_calls) == 1
    final = load_workflow(path)
    assert final.status == WorkflowStatus.FAILED
    assert final.cycles[0].range_status == "FAILED"


def test_salloc_failure_does_not_advance_cycle(tmp_path: Path):
    wf = _wf(tmp_path, cycles=2)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    attempts = {"n": 0}

    def fail_shell(cmd, env):
        attempts["n"] += 1
        return SallocRunResult(returncode=1, combined_output="denied", job_id=None)

    hooks = OrchestratorHooks(
        run_shell=fail_shell,
        run_range=lambda *a: RangeUpdateResult(ok=True, message="x"),
        count_trials=lambda rp: 5,
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={"SLURM_JOB_ID": "1"},
        salloc_retry_sleep_sec=0,
        max_salloc_attempts_per_cycle=2,
    )
    rc = run_orchestrator(path, step_b="x", hooks=hooks)
    assert rc == 1
    assert attempts["n"] == 2
    final = load_workflow(path)
    assert final.current_cycle == 1
    assert all(c.range_status is None for c in final.cycles if c.cycle > 1)


def test_only_one_salloc_at_a_time_logical(orchestrator_harness):
    path, hooks, _, _ = orchestrator_harness
    in_flight = {"active": False}
    calls: list[str] = []

    def tracked_shell(cmd, env):
        assert in_flight["active"] is False
        in_flight["active"] = True
        calls.append(cmd)
        try:
            return SallocRunResult(0, "Granted job allocation 42", "42")
        finally:
            in_flight["active"] = False

    hooks.run_shell = tracked_shell
    run_orchestrator(path, step_b="x", hooks=hooks)
    assert len(calls) == 2


def test_stop_status_aborts(tmp_path: Path):
    wf = _wf(tmp_path, cycles=2)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)

    def stop_after_load(p):
        loaded = load_workflow(p)
        loaded.status = WorkflowStatus.STOPPED
        loaded.phase = WorkflowPhase.STOPPED
        save_workflow(p, loaded)
        return loaded

    hooks = OrchestratorHooks(
        run_shell=lambda c, e: SallocRunResult(0, "Granted job allocation 1", "1"),
        run_range=lambda *a: RangeUpdateResult(ok=True, message="ok"),
        count_trials=lambda rp: 1,
        sleep=lambda _: None,
        load_workflow=stop_after_load,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="x", hooks=hooks)
    assert rc == 0
