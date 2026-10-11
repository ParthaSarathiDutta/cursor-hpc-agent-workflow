"""Time-based first-unpassed hierarchy switching."""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.iterative_loop.hierarchy_constants import (
    DECISION_ALL_PROPERTIES_PASSED,
    DECISION_NO_SWAPPABLE_PROPERTY,
    DECISION_SWITCH,
    DECISION_SWITCH_SKIPPED_MAX,
    ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED,
)
from blast_lib.iterative_loop.hierarchy_decision import decide_after_observation_window
from blast_lib.iterative_loop.hierarchy_pass_counts import (
    property_pass_counts,
    property_passed_in_trial,
    trials_in_observation_window,
)
from blast_lib.iterative_loop.hierarchy_provenance import hierarchy_events_path, hierarchy_epoch_dir
from blast_lib.iterative_loop.hierarchy_window import HierarchyObservationWindow
from blast_lib.iterative_loop.main1_hierarchy import (
    Main1HierarchyError,
    apply_adjacent_swap_to_main1,
    extract_live_property_blocks,
    live_property_order,
    reorder_main1_to_hierarchy,
)
from blast_lib.iterative_loop.orchestrator_core import OrchestratorHooks, run_orchestrator
from blast_lib.iterative_loop.region_provenance import region_dir
from blast_lib.iterative_loop.remote_workflow import (
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    load_workflow,
    save_workflow,
    workflow_json_path,
)
from blast_lib.iterative_loop.selection_strategy import StrategyConfig, load_strategy_config
from blast_lib.trial_details import parse_property_blocks, resolve_stage_order

HIERARCHY = ["lattice", "ce", "eos", "phonon", "elastic"]
FIXTURE_MAIN1 = Path(__file__).resolve().parent / "fixtures" / "minimal_main1_hierarchy.py"
SB_MAIN1 = Path(__file__).resolve().parent / "fixtures" / "sb_main1_hierarchy.py"
PARAMS = "Sb-Sb: 1 2 3 4 5 6 7 8 9 10 11 12 13"


def _stage_block(stage: str, *, passed: bool, metrics: str = "1.0") -> str:
    result = "pass" if passed else "fail"
    if stage == "ce":
        score = "score: cohesive_E ['values']"
    else:
        score = f"score: {stage} ['values']"
    return f"""{score}
return {{'values.obj': {metrics}}}
| *  {result}   'values.maxAE% <= 3'  ->  '1.0 <= 3'
"""


def _trial(*blocks: str, reason: str = "fail") -> dict:
    stage_lines = []
    for b in blocks:
        stage_lines.extend(b.strip().splitlines())
    return {"stage_lines": stage_lines, "reason": reason, "status": "final", "score": 999.0}


def _write_hierarchy_strategy(run: Path, *, window_sec: int = 18000) -> None:
    (run / "strategy.json").write_text(
        json.dumps(
            {
                "orchestrator_strategy": ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED,
                "observation_window_sec": window_sec,
                "active_hierarchy": HIERARCHY,
            }
        )
    )


def _hierarchy_wf(tmp_path: Path, *, window_sec: int = 1) -> RemoteWorkflow:
    blast = tmp_path / "blast"
    blast.mkdir(parents=True, exist_ok=True)
    run = tmp_path / "run"
    (run / "reports").mkdir(parents=True)
    _write_hierarchy_strategy(run, window_sec=window_sec)
    main1 = FIXTURE_MAIN1.read_text()
    (run / "main1.py").write_text(main1)
    (run / "model.json").write_text('{"added": []}\n')
    (run / "mcts_restart.tersoff").write_text("Sb Sb Sb 1 1 2 3 4 5 6 7 8 9 10 11 12 13\n")
    return RemoteWorkflow(
        workflow_id="h1",
        run_folder=str(run),
        walltime="00:10:00",
        total_cycles=1,
        status=WorkflowStatus.QUEUED,
        phase=WorkflowPhase.QUEUED,
        blast_root=str(blast),
        blast_python="/usr/bin/python",
        gpu_account="m4597_g",
        orchestrator_strategy=ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED,
        active_hierarchy=list(HIERARCHY),
        observation_window_sec=window_sec,
    )


def _orchestrator_test_hooks(**overrides) -> OrchestratorHooks:
    base = {
        "run_range": MagicMock(),
        "count_trials": MagicMock(return_value=0),
        "sleep": lambda _: None,
        "load_workflow": load_workflow,
        "save_workflow": save_workflow,
        "env": {},
        "drain_interactive_allocation_fn": lambda *args, **kwargs: "CANCELLED",
        "poll_slurm_job_state": lambda jid: "CANCELLED",
    }
    base.update(overrides)
    return OrchestratorHooks(**base)


# --- Decision examples ---


def test_last_property_zero_passes_swaps_with_predecessor():
    trials = [
        _trial(
            _stage_block("lattice", passed=True),
            _stage_block("ce", passed=True),
            _stage_block("eos", passed=True),
            _stage_block("phonon", passed=True),
            _stage_block("elastic", passed=False),
            reason="elastic MAE% > 25",
        )
    ]
    d = decide_after_observation_window(trials, HIERARCHY)
    assert d.decision == DECISION_SWITCH
    assert d.first_unpassed_property == "elastic"
    assert d.swapped_with_property == "phonon"
    assert d.target_hierarchy == ["lattice", "ce", "eos", "elastic", "phonon"]


def test_middle_property_first_zero_not_elastic():
    trials = [
        _trial(
            _stage_block("lattice", passed=True),
            _stage_block("ce", passed=True),
            _stage_block("eos", passed=True),
            _stage_block("phonon", passed=False),
            reason="phonon failed",
        )
    ]
    d = decide_after_observation_window(trials, HIERARCHY)
    assert d.decision == DECISION_SWITCH
    assert d.first_unpassed_property == "phonon"
    assert d.swapped_with_property == "eos"
    assert d.target_hierarchy == ["lattice", "ce", "phonon", "eos", "elastic"]
    assert d.pass_counts["elastic"] == 0


def test_one_successful_pass_counts_as_passed():
    trials = []
    for _ in range(99):
        trials.append(
            _trial(
                _stage_block("lattice", passed=False),
                reason="lattice maxAE > 3%",
            )
        )
    trials.append(_trial(_stage_block("lattice", passed=True), reason="ce fail"))
    counts = property_pass_counts(trials, HIERARCHY)
    assert counts["lattice"] == 1


def test_all_properties_pass_no_switch():
    trials = [
        _trial(
            _stage_block("lattice", passed=True),
            _stage_block("ce", passed=True),
            _stage_block("eos", passed=True),
            _stage_block("phonon", passed=True),
            _stage_block("elastic", passed=True),
            reason="completed all stages",
        )
    ]
    d = decide_after_observation_window(trials, HIERARCHY)
    assert d.decision == DECISION_ALL_PROPERTIES_PASSED
    assert d.target_hierarchy == HIERARCHY


def test_first_property_zero_no_swappable():
    trials = [_trial(_stage_block("lattice", passed=False), reason="lattice maxAE > 3%")]
    d = decide_after_observation_window(trials, HIERARCHY)
    assert d.decision == DECISION_NO_SWAPPABLE_PROPERTY
    assert d.first_unpassed_property == "lattice"


@pytest.mark.parametrize(
    "stage",
    ["lattice", "ce", "eos", "phonon", "elastic"],
)
def test_property_pass_detection_explicit(stage: str):
    blocks = [_stage_block(s, passed=True) for s in HIERARCHY[: HIERARCHY.index(stage) + 1]]
    trial = _trial(*blocks, reason="fail")
    assert property_passed_in_trial(trial, stage, HIERARCHY)


def test_transitive_pass_phonon_via_elastic_block():
    trial = _trial(
        _stage_block("lattice", passed=True),
        _stage_block("ce", passed=True),
        _stage_block("eos", passed=True),
        _stage_block("phonon", passed=True),
        _stage_block("elastic", passed=False),
        reason="elastic fail",
    )
    assert property_passed_in_trial(trial, "phonon", HIERARCHY)
    assert not property_passed_in_trial(trial, "elastic", HIERARCHY)


def test_runtime_error_not_counted_as_pass():
    trial = _trial(_stage_block("lattice", passed=True), reason="runtime error")
    assert not property_passed_in_trial(trial, "lattice", HIERARCHY)


# --- Window semantics ---


def test_timer_not_reached_no_decision(tmp_path: Path):
    rp = tmp_path / "ho.report"
    rp.write_text("")
    w = HierarchyObservationWindow(
        rp,
        observation_window_sec=3600.0,
        active_hierarchy=HIERARCHY,
        window_started_monotonic=time.monotonic(),
    )
    assert w.evaluate_if_due() is None


def test_timer_reached_inspects_current_window_only(tmp_path: Path):
    rp = tmp_path / "ho.report"
    rp.write_text(
        _report_with_trials(
            [
                _trial(_stage_block("lattice", passed=True), reason="done"),
            ]
        )
    )
    w = HierarchyObservationWindow(
        rp,
        observation_window_sec=0.0,
        active_hierarchy=HIERARCHY,
        scored_trial_start_index=0,
        window_started_monotonic=time.monotonic() - 10,
    )
    d = w.evaluate_if_due()
    assert d is not None
    assert d.pass_counts["lattice"] >= 1


def test_previous_window_pass_does_not_count(tmp_path: Path):
    rp = tmp_path / "ho.report"
    old = _trial(_stage_block("lattice", passed=True), reason="done")
    rp.write_text(_report_with_trials([old]))
    w = HierarchyObservationWindow(
        rp,
        observation_window_sec=0.0,
        active_hierarchy=HIERARCHY,
        scored_trial_start_index=1,
        window_started_monotonic=time.monotonic() - 10,
    )
    d = w.evaluate_if_due()
    assert d is not None
    assert d.pass_counts["lattice"] == 0


def _report_with_trials(trials: list[dict]) -> str:
    parts = []
    for t in trials:
        lines = "\n".join(f"# {ln}" for ln in t["stage_lines"])
        parts.append(f"input {PARAMS}\n{lines}\n# 999.0 | finalObj | {t['reason']}\n")
    return "".join(parts)


def test_trials_in_observation_window_slice(tmp_path: Path):
    rp = tmp_path / "ho.report"
    rp.write_text(_report_with_trials([_trial(_stage_block("lattice", passed=True))] * 3))
    got = trials_in_observation_window(rp, scored_trial_start_index=2)
    assert len(got) == 1


# --- main1 generic swap ---


def test_generic_main1_adjacent_swap_final_blocked():
    source = FIXTURE_MAIN1.read_text()
    updated, target = apply_adjacent_swap_to_main1(
        source,
        active_hierarchy=HIERARCHY,
        first_unpassed="elastic",
    )
    assert target == ["lattice", "ce", "eos", "elastic", "phonon"]
    assert live_property_order(updated) == target
    assert updated.index("elastic_stage") < updated.index("phonon_stage")
    assert "# _dead_elastic" in updated


def test_commented_duplicate_blocks_untouched():
    source = FIXTURE_MAIN1.read_text()
    assert "# prop = 'elastic'" in source
    blocks = extract_live_property_blocks(source)
    assert [b.name for b in blocks] == HIERARCHY


def test_ambiguous_main1_fails_closed():
    bad = "prop = 'lattice'\nprop = 'lattice'\n"
    with pytest.raises(Main1HierarchyError):
        extract_live_property_blocks(bad)


def test_reorder_validates_permutation():
    source = FIXTURE_MAIN1.read_text()
    out = reorder_main1_to_hierarchy(source, ["lattice", "ce", "phonon", "eos", "elastic"])
    assert live_property_order(out) == ["lattice", "ce", "phonon", "eos", "elastic"]


def test_sb_main1_swap_elastic_phonon_parses_and_keeps_footer():
    """Regression: property blocks inside objective() must not move tail after __main__."""
    source = SB_MAIN1.read_text()
    assert live_property_order(source) == HIERARCHY
    updated, target = apply_adjacent_swap_to_main1(
        source,
        active_hierarchy=HIERARCHY,
        first_unpassed="elastic",
    )
    assert target == ["lattice", "ce", "eos", "elastic", "phonon"]
    assert live_property_order(updated) == target
    ast.parse(updated)
    assert updated.index("return HO.lastfinalobj") < updated.index("if __name__")
    assert updated.index("prop = 'phonon'") < updated.index("return HO.lastfinalobj")


# --- Invariants ---


def test_model_and_restart_unchanged_on_switch(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    model = run / "model.json"
    restart = run / "mcts_restart.tersoff"
    model.write_text('{"x": 1}\n')
    restart.write_text("seed\n")
    main1 = FIXTURE_MAIN1.read_text()
    (run / "main1.py").write_text(main1)
    from blast_lib.iterative_loop.hierarchy_switch import apply_hierarchy_switch_local
    from blast_lib.iterative_loop.hierarchy_decision import HierarchyWindowDecision

    decision = HierarchyWindowDecision(
        decision=DECISION_SWITCH,
        active_hierarchy=HIERARCHY,
        target_hierarchy=["lattice", "ce", "eos", "elastic", "phonon"],
        pass_counts={},
        first_unpassed_property="elastic",
        swapped_with_property="phonon",
        trials_in_window=1,
    )
    mb = model.read_bytes()
    rb = restart.read_bytes()
    res = apply_hierarchy_switch_local(run, decision)
    assert res.ok
    assert model.read_bytes() == mb
    assert restart.read_bytes() == rb


# --- Orchestrator ---


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_hierarchy_switch_resets_mcts_not_region(mock_stream: MagicMock, tmp_path: Path):
    wf = _hierarchy_wf(tmp_path, window_sec=0)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)
    (run / "mctree.restart").write_text("tree")
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

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, abort_state=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("777001")
        if on_poll:
            on_poll()
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(
            returncode=0,
            combined_output="ok",
            job_id="777001",
            aborted=True,
            abort_reason="hierarchy_switch",
        )

    mock_stream.side_effect = fake_stream
    real_load = load_workflow

    def load_stop_after_switch(p: Path):
        wf_loaded = real_load(p)
        if wf_loaded.hierarchy_switch_count >= 1:
            wf_loaded.status = WorkflowStatus.STOPPED
        return wf_loaded

    hooks = _orchestrator_test_hooks(
        run_shell=fake_stream,
        load_workflow=load_stop_after_switch,
    )
    code = run_orchestrator(path, step_b="step", hooks=hooks)
    assert code == 0
    wf2 = load_workflow(path)
    assert wf2.hierarchy_switch_count == 1
    assert wf2.active_hierarchy == ["lattice", "ce", "eos", "elastic", "phonon"]
    assert wf2.region == 0
    assert not (run / "mctree.restart").is_file()
    assert hierarchy_epoch_dir(run, 0).is_dir()
    assert not region_dir(run, 0).exists()


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_all_passed_window_does_not_reset_mcts(mock_stream: MagicMock, tmp_path: Path):
    wf = _hierarchy_wf(tmp_path, window_sec=0)
    path = workflow_json_path(wf.run_folder)
    save_workflow(path, wf)
    run = Path(wf.run_folder)
    (run / "mctree.restart").write_text("tree")
    rp = run / "reports" / "ho.report"
    rp.write_text(
        _report_with_trials(
            [
                _trial(
                    _stage_block("lattice", passed=True),
                    _stage_block("ce", passed=True),
                    _stage_block("eos", passed=True),
                    _stage_block("phonon", passed=True),
                    _stage_block("elastic", passed=True),
                    reason="completed all stages",
                )
            ]
        )
    )

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("777002")
        if on_poll:
            on_poll()
        live = load_workflow(path)
        live.status = WorkflowStatus.STOPPED
        save_workflow(path, live)
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(returncode=0, combined_output="ok", job_id="777002", aborted=False)

    mock_stream.side_effect = fake_stream
    hooks = _orchestrator_test_hooks(run_shell=fake_stream)
    run_orchestrator(path, step_b="step", hooks=hooks)
    assert (run / "mctree.restart").is_file()
    assert hierarchy_events_path(run).is_file()
    wf_done = load_workflow(path)
    assert wf_done.observation_window_index >= 1


# --- Parser / strategy defaults ---


def test_resolve_stage_order_default_unchanged():
    assert resolve_stage_order(None) == ["lattice", "ce", "eos", "phonon", "elastic"]


def test_dynamic_stage_order_for_switched_hierarchy():
    swapped = ["lattice", "ce", "phonon", "eos", "elastic"]
    assert resolve_stage_order(swapped)[2] == "phonon"


def test_parse_property_blocks_default_unchanged():
    lines = _stage_block("elastic", passed=True).splitlines()
    blocks = parse_property_blocks(lines)
    assert blocks[0]["stage"] == "elastic"


def test_strategy3_config_unchanged(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "strategy.json").write_text(
        json.dumps(
            {
                "selection_strategy": "elastic",
                "recenter_trigger": "improvement",
                "incumbent_elastic_obj": 30.0,
            }
        )
    )
    cfg = load_strategy_config(run)
    assert cfg.orchestrator_strategy == ""
    assert cfg.selection_strategy == "elastic"


def test_default_strategy_config_no_hierarchy_orchestrator():
    cfg = StrategyConfig()
    assert cfg.orchestrator_strategy == ""


def test_strategy1_fixed_cycle_not_hierarchy_orchestrator(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "strategy.json").write_text("{}")
    cfg = load_strategy_config(run)
    assert not cfg.orchestrator_strategy
    from blast_lib.iterative_loop.selection_strategy import is_time_based_first_unpassed_hierarchy_strategy

    assert not is_time_based_first_unpassed_hierarchy_strategy(cfg)


@patch("blast_lib.iterative_loop.orchestrator_core.stream_shell_run")
def test_max_hierarchy_switches_blocks_second_switch(mock_stream: MagicMock, tmp_path: Path):
    wf = _hierarchy_wf(tmp_path, window_sec=0)
    run = Path(wf.run_folder)
    (run / "strategy.json").write_text(
        json.dumps(
            {
                "orchestrator_strategy": ORCHESTRATOR_TIME_BASED_FIRST_UNPASSED,
                "observation_window_sec": 0,
                "max_hierarchy_switches": 1,
                "active_hierarchy": HIERARCHY,
            }
        )
    )
    path = workflow_json_path(wf.run_folder)
    wf.max_hierarchy_switches = 1
    wf.hierarchy_switch_count = 1
    wf.active_hierarchy = ["lattice", "ce", "eos", "elastic", "phonon"]
    save_workflow(path, wf)
    rp = run / "reports" / "ho.report"
    rp.write_text(
        _report_with_trials(
            [
                _trial(
                    _stage_block("lattice", passed=True),
                    _stage_block("ce", passed=False),
                    reason="ce fail",
                )
            ]
        )
    )

    def fake_stream(cmd, env, on_salloc_granted=None, should_abort=None, on_poll=None, **kw):
        if on_salloc_granted:
            on_salloc_granted("900001")
        if on_poll:
            on_poll()
        live = load_workflow(path)
        live.status = WorkflowStatus.STOPPED
        save_workflow(path, live)
        from blast_lib.iterative_loop.orchestrator_core import SallocRunResult

        return SallocRunResult(0, "ok", "900001", False, None)

    mock_stream.side_effect = fake_stream
    hooks = _orchestrator_test_hooks(run_shell=fake_stream)
    run_orchestrator(path, step_b="step", hooks=hooks)
    events = (run / ".agentic_loop" / "hierarchy_events.jsonl").read_text()
    assert DECISION_SWITCH_SKIPPED_MAX in events
    assert load_workflow(path).hierarchy_switch_count == 1


def test_strategy2_elastic_fixed_cycle_not_hierarchy(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "strategy.json").write_text(
        json.dumps({"selection_strategy": "elastic", "recenter_trigger": "fixed_cycle"})
    )
    cfg = load_strategy_config(run)
    from blast_lib.iterative_loop.selection_strategy import (
        is_improvement_elastic_strategy,
        is_time_based_first_unpassed_hierarchy_strategy,
    )

    assert not is_time_based_first_unpassed_hierarchy_strategy(cfg)
    assert not is_improvement_elastic_strategy(cfg)
