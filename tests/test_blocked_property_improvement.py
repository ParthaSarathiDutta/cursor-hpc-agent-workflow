"""Blocked-property improvement (generalized Strategy 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blast_lib.iterative_loop.blocked_property_improvement_watcher import (
    BlockedPropertyImprovementWatcher,
)
from blast_lib.iterative_loop.blocked_property_metrics import (
    metric_name_for_property,
    property_metric_from_trial,
)
from blast_lib.iterative_loop.blocked_property_state import (
    BLOCKED_PHASE_DISCOVERY,
    BLOCKED_PHASE_OPTIMIZING,
    BlockedPropertyState,
)
from blast_lib.iterative_loop.hierarchy_constants import ORCHESTRATOR_BLOCKED_PROPERTY_IMPROVEMENT
from blast_lib.iterative_loop.selection_strategy import (
    is_blocked_property_improvement_strategy,
    is_improvement_elastic_strategy,
    strategy_config_from_dict,
)
from blast_lib.parser import parse_ho_report

HIERARCHY = ["lattice", "ce", "eos", "phonon", "elastic"]
PARAMS = "Sb-Sb: 1 2 3 4 5 6 7 8 9 10 11 12 13"


def _trial_lines(*blocks: str) -> dict:
    stage_lines = []
    for b in blocks:
        stage_lines.extend(b.strip().splitlines())
    return {"stage_lines": stage_lines, "status": "final", "score": 999.0, "reason": "fail"}


def _lattice_block(*, passed: bool, obj: float = 10.0) -> str:
    r = "pass" if passed else "fail"
    return f"""score: lattice ['values']
return {{'values.obj': {obj}, 'values.maxAE%': 1.0}}
| *  {r}   'values.maxAE% <= 3'  ->  '1.0 <= 3'
"""


def _ce_block(*, passed: bool, obj: float = 5.0) -> str:
    r = "pass" if passed else "fail"
    return f"""score: cohesive_E ['values']
return {{'values.obj': {obj}, 'values.maxAE%': 1.0}}
| *  {r}   'values.maxAE%<=3'  ->  '1.0 <= 3'
"""


def _eos_block(*, passed: bool, shape: float = 100.0, shift: float = 10.0) -> str:
    r = "pass" if passed else "fail"
    return f"""score: eos ['shape', 'shift']
return {{'shape.obj': {shape}, 'shift.obj': {shift}}}
| *  {r}   'shape.obj <= 166'  ->  '{shape} <= 166'
"""


def _phonon_block(*, passed: bool, ceil_mae: float = 40.0) -> str:
    r = "pass" if passed else "fail"
    return f"""score: phonon ['neg','gap','shape','ceil','gamma']
return {{'ceil.maxAE%': {ceil_mae}, 'ceil.obj': 10.0}}
| *  {r}   'ceil.maxAE% <= 30.20'  ->  '{ceil_mae} <= 30.20'
"""


def _elastic_block(*, passed: bool, obj: float = 50.0) -> str:
    r = "pass" if passed else "fail"
    return f"""score: elastic ['values']
return {{'values.obj': {obj}, 'values.MAE%': 20.0}}
| *  {r}   'values.MAE% <= 30'  ->  '20.0 <= 30'
"""


def _write_report(path: Path, *trial_blocks: str) -> None:
    parts = []
    for i, block in enumerate(trial_blocks, start=1):
        lines = "\n".join(f"# {ln}" for ln in block.strip().splitlines())
        parts.append(f"input {PARAMS}\n{lines}\n# 999{i}.0 | finalObj | done\n")
    path.write_text("".join(parts))


def _state_with_passed(prefix_passed: list[str]) -> BlockedPropertyState:
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    for p in prefix_passed:
        st.property_passed_ever[p] = True
        st.property_reached_ever[p] = True
    return st


# --- A Detection ---


def test_detection_target_phonon_when_ladder_passed_through_eos():
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    trial = _trial_lines(
        _lattice_block(passed=True),
        _ce_block(passed=True),
        _eos_block(passed=True),
        _phonon_block(passed=False, ceil_mae=40.0),
    )
    st.ingest_trial(trial)
    assert st.discover_target_if_needed() == "phonon"
    assert st.phase == BLOCKED_PHASE_OPTIMIZING


# --- B Improvement ---


def test_phonon_improvement_triggers(tmp_path: Path):
    rp = tmp_path / "ho.report"
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    st.property_reached_ever["phonon"] = True
    st.target_property = "phonon"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=40.0, improvement_tolerance=0.01
    )
    _write_report(rp, _phonon_block(passed=False, ceil_mae=40.0))
    assert w.poll() is None
    rp.write_text(rp.read_text() + _report_append(_phonon_block(passed=False, ceil_mae=35.0)))
    trig = w.poll()
    assert trig is not None
    assert trig.target_property == "phonon"
    assert trig.candidate_property_metric == pytest.approx(35.0)


def _report_append(block: str) -> str:
    lines = "\n".join(f"# {ln}" for ln in block.strip().splitlines())
    return f"input {PARAMS}\n{lines}\n# 9992.0 | finalObj | done\n"


# --- C Persistence across fresh report ---


def test_target_persists_after_fresh_report(tmp_path: Path):
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    st.target_property = "phonon"
    st.property_reached_ever["phonon"] = True
    st.phase = BLOCKED_PHASE_OPTIMIZING
    rp = tmp_path / "ho.report"
    rp.write_text("")
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=None, improvement_tolerance=0.01
    )
    w.poll()
    assert w.state.target_property == "phonon"


# --- D Multiple regions ---


def test_target_remains_phonon_across_two_recenters(tmp_path: Path):
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    for p in ("lattice", "ce", "eos"):
        st.property_passed_ever[p] = True
    st.target_property = "phonon"
    st.property_reached_ever["phonon"] = True
    rp = tmp_path / "ho.report"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=40.0, improvement_tolerance=0.01
    )
    _write_report(rp, _phonon_block(passed=False, ceil_mae=40.0))
    w.poll()
    rp.write_text(rp.read_text() + _report_append(_phonon_block(passed=False, ceil_mae=35.0)))
    assert w.poll() is not None
    w.reset_baseline()
    w.incumbent_property_obj = 35.0
    rp.write_text(rp.read_text() + _report_append(_phonon_block(passed=False, ceil_mae=31.0)))
    trig2 = w.poll()
    assert trig2 is not None
    assert w.state.target_property == "phonon"


# --- E Pass advancement ---


def test_phonon_pass_advances_target_to_elastic(tmp_path: Path):
    st = _state_with_passed(["lattice", "ce", "eos"])
    st.target_property = "phonon"
    st.property_reached_ever["phonon"] = True
    rp = tmp_path / "ho.report"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=40.0, improvement_tolerance=0.01
    )
    _write_report(rp, _phonon_block(passed=True, ceil_mae=25.0))
    assert w.poll() is None
    assert w.last_target_advanced is not None
    assert w.last_target_advanced.old_target_property == "phonon"
    assert w.state.property_passed_ever["phonon"] is True


def test_elastic_becomes_target_after_phonon_passed():
    st = _state_with_passed(["lattice", "ce", "eos"])
    st.property_reached_ever["phonon"] = True
    st.property_reached_ever["elastic"] = True
    trial = _trial_lines(
        _phonon_block(passed=True, ceil_mae=25.0),
    )
    st.target_property = "phonon"
    st.ingest_trial(trial)
    st.advance_after_target_passed()
    assert st.discover_target_if_needed() == "elastic"


# --- F Pass beats improvement ---


def test_pass_advances_without_improvement_trigger(tmp_path: Path):
    st = _state_with_passed(["lattice", "ce", "eos"])
    st.target_property = "phonon"
    st.property_reached_ever["phonon"] = True
    rp = tmp_path / "ho.report"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=40.0, improvement_tolerance=0.01
    )
    _write_report(rp, _phonon_block(passed=True, ceil_mae=25.0))
    assert w.poll() is None
    assert w.last_improvement is None
    assert w.last_target_advanced is not None


# --- G New target incumbent ---


def test_elastic_incumbent_not_reused_from_phonon(tmp_path: Path):
    st = _state_with_passed(["lattice", "ce", "eos", "phonon"])
    st.target_property = "elastic"
    st.property_reached_ever["elastic"] = True
    rp = tmp_path / "ho.report"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=None, improvement_tolerance=0.01
    )
    _write_report(rp, _elastic_block(passed=False, obj=34.0))
    w.poll()
    assert w.incumbent_property_obj == pytest.approx(34.0)


# --- H Elastic target improvement ---


def test_elastic_metric_improvement_triggers(tmp_path: Path):
    rp = tmp_path / "ho.report"
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    st.target_property = "elastic"
    st.property_reached_ever["elastic"] = True
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=40.0, improvement_tolerance=0.01
    )
    _write_report(rp, _elastic_block(passed=False, obj=40.0))
    w.poll()
    rp.write_text(rp.read_text() + _report_append(_elastic_block(passed=False, obj=35.0)))
    trig = w.poll()
    assert trig is not None
    assert trig.target_property == "elastic"


# --- I All passed ---


def test_all_properties_passed():
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    for p in HIERARCHY:
        st.property_passed_ever[p] = True
    assert st.all_passed()
    assert st.discover_target_if_needed() is None


# --- J Missing metric ---


def test_no_trigger_when_target_stage_missing(tmp_path: Path):
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    st.target_property = "phonon"
    rp = tmp_path / "ho.report"
    w = BlockedPropertyImprovementWatcher(
        rp, state=st, incumbent_property_obj=None, improvement_tolerance=0.01
    )
    _write_report(rp, _lattice_block(passed=False))
    assert w.poll() is None


# --- K Fresh report safety ---


def test_pass_state_persists_in_workflow_not_report(tmp_path: Path):
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    trial = _trial_lines(_lattice_block(passed=True))
    st.ingest_trial(trial)
    assert st.property_passed_ever["lattice"] is True
    rp = tmp_path / "ho.report"
    rp.write_text("")
    st2 = BlockedPropertyState(
        active_hierarchy=HIERARCHY,
        property_passed_ever=dict(st.property_passed_ever),
        property_reached_ever=dict(st.property_reached_ever),
    )
    assert st2.property_passed_ever["lattice"] is True


# --- Metrics ---


def test_property_metrics():
    t = _trial_lines(_phonon_block(passed=False, ceil_mae=33.3))
    assert property_metric_from_trial(t, "phonon") == pytest.approx(33.3)
    t2 = _trial_lines(_eos_block(passed=False, shape=120.0, shift=15.0))
    assert property_metric_from_trial(t2, "eos") == pytest.approx(120.0)
    assert metric_name_for_property("phonon") == "ceil.maxAE%"


# --- L Compatibility ---


def test_legacy_elastic_strategy_predicate_unchanged():
    cfg = strategy_config_from_dict(
        {"selection_strategy": "elastic", "recenter_trigger": "improvement"}
    )
    assert is_improvement_elastic_strategy(cfg)
    blocked = strategy_config_from_dict(
        {"orchestrator_strategy": ORCHESTRATOR_BLOCKED_PROPERTY_IMPROVEMENT}
    )
    assert is_blocked_property_improvement_strategy(blocked)
    assert not is_improvement_elastic_strategy(blocked)


def test_zero_trials_stays_discovery():
    st = BlockedPropertyState(active_hierarchy=HIERARCHY)
    assert st.discover_target_if_needed() is None
    assert st.phase == BLOCKED_PHASE_DISCOVERY


def test_ho_report_roundtrip_parse(tmp_path: Path):
    rp = tmp_path / "ho.report"
    _write_report(rp, _phonon_block(passed=False, ceil_mae=40.0))
    trials = parse_ho_report(rp)
    assert len(trials) == 1
    assert property_metric_from_trial(trials[0], "phonon") == pytest.approx(40.0)
