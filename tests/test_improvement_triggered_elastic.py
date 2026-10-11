"""Strategy 3 orchestrator — improvement-triggered elastic recenter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.iterative_loop.orchestrator_core import (
    OrchestratorHooks,
    run_orchestrator,
)
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.iterative_loop.recenter_trigger import RECENTER_IMPROVEMENT
from blast_lib.iterative_loop.region_provenance import improvement_events_path, region_dir
from blast_lib.iterative_loop.remote_workflow import (
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)
from blast_lib.iterative_loop.selection_strategy import STRATEGY_ELASTIC
from tests.test_elastic_improvement_watcher import PARAMS, _elastic_trial_block

FIXTURE_PARAMS = PARAMS


def _write_strategy(run: Path, *, incumbent: float = 34.0, max_regions: int = 5) -> None:
    (run / "strategy.json").write_text(
        json.dumps(
            {
                "selection_strategy": STRATEGY_ELASTIC,
                "recenter_trigger": RECENTER_IMPROVEMENT,
                "improvement_tolerance": 0.01,
                "incumbent_elastic_obj": incumbent,
                "max_regions": max_regions,
            }
        )
    )


def _improvement_wf(tmp_path: Path, *, max_regions: int = 3) -> RemoteWorkflow:
    run = tmp_path / "run"
    (run / "reports").mkdir(parents=True)
    _write_strategy(run, max_regions=max_regions)
    (run / "mcts_restart.tersoff").write_text(
        "Sb Sb Sb 1 1 2 3 4 5 6 7 8 9 10 11 12 13\n"
    )
    return RemoteWorkflow(
        workflow_id="imp1",
        run_folder=str(run),
        walltime="00:10:00",
        total_cycles=1,
        status=WorkflowStatus.QUEUED,
        phase=WorkflowPhase.QUEUED,
        blast_root="/blast",
        blast_python="/usr/bin/python",
        gpu_account="m4597_g",
        incumbent_elastic_obj=34.0,
        max_regions=max_regions,
    )


@patch("blast_lib.iterative_loop.orchestrator_core.apply_recenter_from_trial")
@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_improvement_triggers_recenter_and_fresh_region(
    mock_stream: MagicMock,
    mock_recenter: MagicMock,
    tmp_path: Path,
):
    wf = _improvement_wf(tmp_path, max_regions=1)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)
    rp = run / "reports" / "ho.report"
    mock_recenter.return_value = RangeUpdateResult(
        ok=True,
        message="ok",
        best_iteration=1,
        elastic_values_obj=33.5,
    )

    call_n = {"n": 0}

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, abort_state=None, **kw):
        call_n["n"] += 1
        if on_salloc_granted:
            on_salloc_granted("888001")
        rp.write_text(_elastic_trial_block(33.5))
        if on_poll:
            on_poll()
        if abort_state:
            assert abort_state.get("reason") == "improvement"
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(
            returncode=0,
            combined_output="Granted job allocation 888001",
            job_id="888001",
            aborted=True,
            abort_reason="improvement",
        )

    mock_stream.side_effect = fake_stream

    hooks = OrchestratorHooks(
        run_shell=lambda *a, **k: None,
        run_range=lambda *a: RangeUpdateResult(ok=True, message="x"),
        count_trials=lambda rp: 1,
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)

    assert rc == 0
    mock_stream.assert_called_once()
    assert mock_stream.call_args.kwargs["abort_state"]["reason"] == "improvement"
    mock_recenter.assert_called_once()
    trial_arg = mock_recenter.call_args[0][2]
    assert FIXTURE_PARAMS.split(": ", 1)[1].split()[0] in (trial_arg.get("input_params") or "")

    final = load_workflow(path)
    assert final.incumbent_elastic_obj == pytest.approx(33.5)
    assert final.region == 1
    assert not rp.is_file()
    assert (region_dir(run, 0) / "ho.report").is_file()
    assert improvement_events_path(run).is_file()


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_walltime_no_improvement_reallocates_same_region(mock_stream: MagicMock, tmp_path: Path):
    wf = _improvement_wf(tmp_path, max_regions=5)
    wf.max_total_runtime_sec = 60
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    recenter_calls = {"n": 0}
    alloc_calls = {"n": 0}

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, abort_state=None, **kw):
        alloc_calls["n"] += 1
        if on_salloc_granted:
            on_salloc_granted("777001")
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(
            returncode=0,
            combined_output="timeout",
            job_id="777001",
            aborted=False,
            abort_reason=None,
        )

    mock_stream.side_effect = fake_stream

    budget_checks = {"n": 0}

    def fake_runtime_exceeded(wf_obj):
        budget_checks["n"] += 1
        return budget_checks["n"] > 3

    with patch(
        "blast_lib.iterative_loop.orchestrator_core.apply_recenter_from_trial",
        side_effect=lambda *a, **k: recenter_calls.__setitem__("n", recenter_calls["n"] + 1),
    ), patch(
        "blast_lib.iterative_loop.orchestrator_core._runtime_budget_exceeded",
        side_effect=fake_runtime_exceeded,
    ):
        hooks = OrchestratorHooks(
            run_shell=lambda *a, **k: None,
            run_range=lambda *a: RangeUpdateResult(ok=True, message="x"),
            count_trials=lambda rp: 0,
            sleep=lambda _: None,
            load_workflow=load_workflow,
            save_workflow=save_workflow,
            env={},
        )
        rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)

    assert rc == 0
    assert alloc_calls["n"] >= 2
    assert recenter_calls["n"] == 0
    final = load_workflow(path)
    assert final.region == 0
    assert final.incumbent_elastic_obj == pytest.approx(34.0)


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_max_regions_completes_after_improvement(mock_stream: MagicMock, tmp_path: Path):
    wf = _improvement_wf(tmp_path, max_regions=1)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)
    rp = run / "reports" / "ho.report"

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, abort_state=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("666001")
        rp.write_text(_elastic_trial_block(33.0))
        if on_poll:
            on_poll()
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(
            returncode=0,
            combined_output="",
            job_id="666001",
            aborted=True,
            abort_reason="improvement",
        )

    mock_stream.side_effect = fake_stream

    with patch(
        "blast_lib.iterative_loop.orchestrator_core.apply_recenter_from_trial",
        return_value=RangeUpdateResult(ok=True, message="ok", elastic_values_obj=33.0),
    ):
        hooks = OrchestratorHooks(
            run_shell=lambda *a, **k: None,
            run_range=lambda *a: RangeUpdateResult(ok=True, message="x"),
            count_trials=lambda rp: 1,
            sleep=lambda _: None,
            load_workflow=load_workflow,
            save_workflow=save_workflow,
            env={},
        )
        rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)

    assert rc == 0
    final = load_workflow(path)
    assert final.status == WorkflowStatus.COMPLETED
    assert final.region == 1


@patch("blast_lib.iterative_loop.range_core.subprocess.run")
def test_apply_recenter_writes_mcts_restart(mock_run: MagicMock, tmp_path: Path):
    from blast_lib.iterative_loop.range_core import apply_recenter_from_trial

    run = tmp_path / "run"
    run.mkdir()
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    trial = {
        "input_params": PARAMS.split(": ", 1)[1],
        "iteration": 1,
        "score": 999.0,
    }
    result = apply_recenter_from_trial(
        run,
        "python",
        trial,
        selection_strategy=STRATEGY_ELASTIC,
    )
    assert result.ok
    cmd = mock_run.call_args[0][0]
    assert "changemodel.json.py" in cmd
    for token in ["1.0", "13.0"]:
        assert token in cmd
    restart = (run / "mcts_restart.tersoff").read_text()
    assert "1.0" in restart and "13.0" in restart


def test_fixed_cycle_still_used_without_improvement_trigger(tmp_path: Path):
    run = tmp_path / "run"
    (run / "reports").mkdir(parents=True)
    (run / "reports" / "ho.report").write_text(
        "input x\n# 100.0 | finalObj |\n"
    )
    (run / "strategy.json").write_text(json.dumps({"selection_strategy": "elastic"}))

    wf = RemoteWorkflow(
        workflow_id="fix",
        run_folder=str(run),
        walltime="00:02:00",
        total_cycles=1,
        status=WorkflowStatus.QUEUED,
        phase=WorkflowPhase.QUEUED,
        blast_root="/blast",
        blast_python="/usr/bin/python",
        gpu_account="m4597_g",
        cycles=[],
    )
    from blast_lib.iterative_loop.remote_workflow import CycleRecord

    wf.cycles = [CycleRecord(cycle=1)]
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)

    from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

    def run_shell(cmd, env, on_salloc_granted=None, should_abort=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("90001")
        return SallocRunResult(0, "Granted job allocation 90001", "90001")

    hooks = OrchestratorHooks(
        run_shell=run_shell,
        run_range=lambda *a: RangeUpdateResult(
            ok=True, message="ok", best_score=1.0, best_iteration=1, gpu_elapsed_sec=120
        ),
        count_trials=lambda rp: 2,
        sleep=lambda _: None,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env={},
    )
    rc = run_orchestrator(path, step_b="echo gpu", hooks=hooks)
    assert rc == 0
    final = load_workflow(path)
    assert final.status == WorkflowStatus.COMPLETED
    assert final.cycles[0].range_status == "COMPLETED"
