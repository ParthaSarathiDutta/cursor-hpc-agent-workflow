"""Execution hardening for time-based hierarchy orchestrator (not decision logic)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.iterative_loop.hierarchy_constants import ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED
from blast_lib.iterative_loop.orchestrator_core import OrchestratorHooks, SallocRunResult, run_orchestrator
from blast_lib.iterative_loop.remote_workflow import (
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    ensure_orchestrator_job_id_from_environment,
    load_workflow,
    save_workflow,
    workflow_json_path,
)
from blast_lib.iterative_loop.salloc_run_log import salloc_log_path
from tests.test_time_based_hierarchy import (
    FIXTURE_MAIN1,
    HIERARCHY,
    _hierarchy_wf,
    _orchestrator_test_hooks,
    _report_with_trials,
    _stage_block,
    _trial,
    _write_hierarchy_strategy,
)


def _prepare_minimal_run(tmp_path: Path, *, window_sec: int = 3600) -> tuple[Path, RemoteWorkflow]:
    wf = _hierarchy_wf(tmp_path, window_sec=window_sec)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    return path, wf


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_failed_allocation_triggers_backoff(mock_stream: MagicMock, tmp_path: Path):
    path, wf = _prepare_minimal_run(tmp_path)
    sleeps: list[float] = []

    def fail_run(*args, **kwargs):
        return SallocRunResult(
            returncode=1,
            combined_output="salloc: denied",
            job_id="880001",
            terminal_slurm_state="FAILED",
        )

    mock_stream.side_effect = fail_run
    hooks = _orchestrator_test_hooks(
        run_shell=mock_stream,
        sleep=sleeps.append,
        salloc_retry_sleep_sec=42.0,
        max_consecutive_failed_allocations=5,
    )

    def stop_after_one_fail(p: Path):
        loaded = load_workflow(p)
        if loaded.consecutive_failed_allocations >= 1:
            loaded.status = WorkflowStatus.STOPPED
        return loaded

    hooks.load_workflow = stop_after_one_fail  # type: ignore[method-assign]

    run_orchestrator(path, step_b="step", hooks=hooks)
    assert sleeps == [42.0]
    log = salloc_log_path(Path(wf.run_folder), "880001")
    assert log.is_file()
    assert "denied" in log.read_text()


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_consecutive_failures_fail_closed(mock_stream: MagicMock, tmp_path: Path):
    path, _wf = _prepare_minimal_run(tmp_path)
    (Path(_wf.run_folder) / "strategy.json").write_text(
        json.dumps(
            {
                "orchestrator_strategy": ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED,
                "observation_window_sec": 3600,
                "max_consecutive_failed_allocations": 3,
                "active_hierarchy": HIERARCHY,
            }
        )
    )

    mock_stream.return_value = SallocRunResult(
        1,
        "boom",
        "880002",
        terminal_slurm_state="FAILED",
    )
    hooks = _orchestrator_test_hooks(
        run_shell=mock_stream,
        salloc_retry_sleep_sec=0.0,
        max_consecutive_failed_allocations=3,
    )
    code = run_orchestrator(path, step_b="step", hooks=hooks)
    assert code == 1
    wf2 = load_workflow(path)
    assert wf2.status == WorkflowStatus.FAILED
    assert wf2.consecutive_failed_allocations >= 3
    assert mock_stream.call_count == 3


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_timeout_resets_failure_counter(mock_stream: MagicMock, tmp_path: Path):
    path, wf = _prepare_minimal_run(tmp_path)
    calls = {"n": 0}

    def seq(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return SallocRunResult(1, "fail", "880003", terminal_slurm_state="FAILED")
        return SallocRunResult(0, "ok", "880004", terminal_slurm_state="TIMEOUT")

    mock_stream.side_effect = seq
    real_load = load_workflow

    def load_stop_after_recovery(p: Path):
        loaded = real_load(p)
        if mock_stream.call_count >= 2 and loaded.consecutive_failed_allocations == 0:
            loaded.status = WorkflowStatus.STOPPED
        return loaded

    hooks = _orchestrator_test_hooks(
        run_shell=mock_stream,
        salloc_retry_sleep_sec=0.0,
        load_workflow=load_stop_after_recovery,
    )
    run_orchestrator(path, step_b="step", hooks=hooks)
    wf_mid = load_workflow(path)
    assert wf_mid.consecutive_failed_allocations == 0


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_productive_allocation_resets_failure_counter(mock_stream: MagicMock, tmp_path: Path):
    path, wf = _prepare_minimal_run(tmp_path)
    run = Path(wf.run_folder)
    rp = run / "reports" / "ho.report"
    rp.write_text(_report_with_trials([_trial(_stage_block("lattice", passed=True))]))
    calls = {"n": 0}

    def seq(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return SallocRunResult(1, "fail", "880005", terminal_slurm_state="FAILED")
        rp.write_text(
            _report_with_trials(
                [
                    _trial(_stage_block("lattice", passed=True)),
                    _trial(_stage_block("lattice", passed=False), reason="fail"),
                ]
            )
        )
        return SallocRunResult(1, "fail2", "880006", terminal_slurm_state="FAILED")

    mock_stream.side_effect = seq
    from blast_lib.iterative_loop.ho_report_local import require_scored_trials_count

    real_load = load_workflow

    def load_stop_after_growth(p: Path):
        loaded = real_load(p)
        if mock_stream.call_count >= 2 and loaded.consecutive_failed_allocations == 0:
            loaded.status = WorkflowStatus.STOPPED
        return loaded

    hooks = _orchestrator_test_hooks(
        run_shell=mock_stream,
        count_trials=require_scored_trials_count,
        salloc_retry_sleep_sec=0.0,
        load_workflow=load_stop_after_growth,
    )
    run_orchestrator(path, step_b="step", hooks=hooks)
    assert load_workflow(path).consecutive_failed_allocations == 0


@patch("blast_lib.iterative_loop.orchestrator_core.apply_hierarchy_switch_local")
@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_switch_waits_for_drain_before_main1(
    mock_stream: MagicMock,
    mock_switch: MagicMock,
    tmp_path: Path,
):
    path, wf = _prepare_minimal_run(tmp_path, window_sec=0)
    run = Path(wf.run_folder)
    rp = run / "reports" / "ho.report"
    rp.write_text(
        _report_with_trials(
            [
                _trial(
                    _stage_block("lattice", passed=True),
                    _stage_block("ce", passed=True),
                    _stage_block("eos", passed=True),
                    _stage_block("phonon", passed=True),
                    _stage_block("elastic", passed=False),
                    reason="elastic fail",
                )
            ]
        )
    )
    order: list[str] = []

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("880007")
        if on_poll:
            on_poll()
        return SallocRunResult(
            0,
            "ok",
            "880007",
            aborted=True,
            abort_reason="hierarchy_switch",
        )

    mock_stream.side_effect = fake_stream

    def drain(*args, **kwargs):
        order.append("drain")
        return "CANCELLED"

    def switch(run_folder, decision):
        order.append("switch")
        from blast_lib.iterative_loop.hierarchy_switch import HierarchySwitchResult

        return HierarchySwitchResult(
            ok=True,
            message="ok",
            target_hierarchy=["lattice", "ce", "eos", "elastic", "phonon"],
            main1_sha256_before="a",
            main1_sha256_after="b",
            model_json_sha256="c",
            mcts_restart_sha256="d",
        )

    mock_switch.side_effect = switch

    hooks = _orchestrator_test_hooks(
        run_shell=fake_stream,
        drain_interactive_allocation_fn=drain,
    )

    def stop_after_switch(p: Path):
        loaded = load_workflow(p)
        if loaded.hierarchy_switch_count >= 1:
            loaded.status = WorkflowStatus.STOPPED
        return loaded

    hooks.load_workflow = stop_after_switch  # type: ignore[method-assign]
    run_orchestrator(path, step_b="step", hooks=hooks)
    assert order == ["drain", "switch"]


def test_ensure_orchestrator_job_id_from_environment():
    wf = RemoteWorkflow(
        workflow_id="x",
        run_folder="/tmp/run",
        walltime="00:10:00",
        total_cycles=1,
    )
    out = ensure_orchestrator_job_id_from_environment(wf, {"SLURM_JOB_ID": "59655477"})
    assert out.orchestrator_job_id == "59655477"
    out2 = ensure_orchestrator_job_id_from_environment(out, {"SLURM_JOB_ID": "999"})
    assert out2.orchestrator_job_id == "59655477"


def test_salloc_log_path_deterministic(tmp_path: Path):
    run = tmp_path / "run"
    p = salloc_log_path(run, "12345")
    assert p == run / ".agentic_loop" / "logs" / "salloc-12345.out"
