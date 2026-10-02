"""Fresh vs continue ho.report history at workflow start (orchestrator + helpers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.iterative_loop.ho_report_local import (
    best_trial_from_report,
    count_scored_trials,
    history_mode_for_cycle_start,
    ho_report_path_for_run,
    require_scored_trials_count,
    scored_trials_before_cycle,
)
from blast_lib.iterative_loop.orchestrator_core import OrchestratorHooks, SallocRunResult, run_orchestrator
from blast_lib.iterative_loop.range_core import run_range_update_local
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.iterative_loop.remote_workflow import (
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)
from tests.test_orchestrator_core import _minimal_ho_report, _wf


def test_scored_trials_before_cycle_continue(tmp_path: Path):
    run = tmp_path / "run"
    (run / "reports").mkdir(parents=True)
    rp = run / "reports" / "ho.report"
    rp.write_text(_minimal_ho_report(10.0, 20.0))
    assert scored_trials_before_cycle(rp, cycle=1) == 2
    assert history_mode_for_cycle_start(rp, cycle=1) == "continue"


def test_scored_trials_before_cycle_fresh_cycle1(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    rp = run / "reports" / "ho.report"
    assert not rp.is_file()
    assert scored_trials_before_cycle(rp, cycle=1) == 0
    assert history_mode_for_cycle_start(rp, cycle=1) == "fresh"


def test_scored_trials_before_cycle_missing_fails_cycle2(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    rp = ho_report_path_for_run(run)
    with pytest.raises(FileNotFoundError, match="cycle 2"):
        scored_trials_before_cycle(rp, cycle=2)


def test_require_scored_trials_count_missing_after_gpu(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    rp = ho_report_path_for_run(run)
    with pytest.raises(FileNotFoundError, match="after GPU"):
        require_scored_trials_count(rp)


def test_best_trial_still_minimum_finalobj(tmp_path: Path):
    run = tmp_path / "run"
    (run / "reports").mkdir(parents=True)
    rp = run / "reports" / "ho.report"
    rp.write_text(_minimal_ho_report(500.0, 50.0, 200.0))
    best = best_trial_from_report(rp)
    assert best["score"] == 50.0


def test_fresh_cycle1_starts_without_report(tmp_path: Path):
    wf = _wf(tmp_path, cycles=1, with_report=False)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    salloc_ran = {"n": 0}

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None):
        salloc_ran["n"] += 1
        if on_salloc_granted:
            on_salloc_granted("90001")
        return SallocRunResult(0, "Granted job allocation 90001", "90001")

    def run_range(rf, py, before, jid, wt):
        assert before == 0
        rp = rf / "reports" / "ho.report"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(_minimal_ho_report(99.0))
        return RangeUpdateResult(
            ok=True,
            message="ok",
            best_score=99.0,
            best_iteration=1,
            gpu_elapsed_sec=120,
        )

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=run_range,
        count_trials=lambda rp: count_scored_trials(rp),
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 0
    assert salloc_ran["n"] == 1
    final = load_workflow(path)
    assert final.history_mode == "fresh"
    assert final.cycles[0].scored_trials_before == 0
    assert final.cycles[0].scored_trials_after == 1


def test_fresh_cycle1_missing_report_after_gpu_fails(tmp_path: Path, monkeypatch):
    wf = _wf(tmp_path, cycles=1, with_report=False)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)

    monkeypatch.setattr(
        "blast_lib.iterative_loop.range_core.fetch_job_elapsed_seconds_local",
        lambda _jid: 120,
    )
    monkeypatch.setattr(
        "blast_lib.iterative_loop.range_core.allocation_met_walltime",
        lambda _e, _w: (True, 60),
    )

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None):
        if on_salloc_granted:
            on_salloc_granted("90001")
        return SallocRunResult(0, "Granted job allocation 90001", "90001")

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=lambda *a: run_range_update_local(*a[:2], scored_before=a[2], gpu_job_id=a[3], walltime=a[4]),
        count_trials=lambda rp: count_scored_trials(rp),
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 1
    final = load_workflow(path)
    assert final.status == WorkflowStatus.FAILED
    assert "Missing ho.report" in (final.error or "")


def test_fresh_cycle1_zero_scored_trials_fails(tmp_path: Path, monkeypatch):
    wf = _wf(tmp_path, cycles=1, with_report=False)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)

    monkeypatch.setattr(
        "blast_lib.iterative_loop.range_core.fetch_job_elapsed_seconds_local",
        lambda _jid: 120,
    )
    monkeypatch.setattr(
        "blast_lib.iterative_loop.range_core.allocation_met_walltime",
        lambda _e, _w: (True, 60),
    )

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None):
        if on_salloc_granted:
            on_salloc_granted("90001")
        return SallocRunResult(0, "Granted job allocation 90001", "90001")

    def run_range(rf, py, before, jid, wt):
        rp = rf / "reports" / "ho.report"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("not a scored trial\n")
        return run_range_update_local(rf, py, scored_before=before, gpu_job_id=jid, walltime=wt)

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=run_range,
        count_trials=lambda rp: count_scored_trials(rp),
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 1
    final = load_workflow(path)
    assert "No new scored trials" in (final.error or "")


def test_report_disappears_before_cycle2_fails(tmp_path: Path):
    wf = _wf(tmp_path, cycles=2, with_report=True)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)
    calls = {"n": 0}
    removed = {"done": False}

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None):
        calls["n"] += 1
        if on_salloc_granted:
            on_salloc_granted(f"9000{calls['n']}")
        return SallocRunResult(0, f"Granted job allocation 9000{calls['n']}", f"9000{calls['n']}")

    def run_range(rf, py, before, jid, wt):
        rp = rf / "reports" / "ho.report"
        text = rp.read_text()
        rp.write_text(text + _minimal_ho_report(80.0))
        return RangeUpdateResult(
            ok=True,
            message="ok",
            best_score=80.0,
            best_iteration=2,
            gpu_elapsed_sec=120,
        )

    def save_hook(path, wf):
        save_workflow(path, wf)
        c1 = wf.cycle_record(1)
        if c1.range_status == "COMPLETED" and not removed["done"]:
            (run / "reports" / "ho.report").unlink(missing_ok=True)
            removed["done"] = True

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=run_range,
        count_trials=lambda rp: count_scored_trials(rp) if rp.is_file() else 0,
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_hook,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 1
    final = load_workflow(path)
    assert final.status == WorkflowStatus.FAILED
    assert "before cycle 2" in (final.error or "").lower()
    assert len([c for c in final.cycles if c.gpu_job_id]) == 1


def test_continue_history_preserves_existing_count(tmp_path: Path):
    wf = _wf(tmp_path, cycles=1, with_report=True)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    rp = Path(wf.run_folder) / "reports" / "ho.report"
    assert count_scored_trials(rp) == 1

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None):
        if on_salloc_granted:
            on_salloc_granted("90001")
        return SallocRunResult(0, "Granted job allocation 90001", "90001")

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=lambda *a: RangeUpdateResult(
            ok=True, message="ok", best_score=1.0, best_iteration=1, gpu_elapsed_sec=120
        ),
        count_trials=lambda rp: count_scored_trials(rp),
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 0
    final = load_workflow(path)
    assert final.history_mode == "continue"
    assert final.cycles[0].scored_trials_before == 1
