"""Elastic improvement watcher — trigger semantics."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from blast_lib.iterative_loop.elastic_improvement_watcher import ElasticImprovementWatcher
from blast_lib.iterative_loop.recenter_trigger import TOLERANCE_NOT_VALIDATED_NOTE

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "iter21750_stage_lines.txt"
PARAMS = "Sb-Sb: 1.0 2.0 3.0 4.0 5.0 6.0 7.0 8.0 9.0 10.0 11.0 12.0 13.0"


def _elastic_trial_block(elastic_obj: float) -> str:
    """Minimal scored trial with one elastic block (values.obj is the elastic metric)."""
    stage = f"""score: elastic ['values']  (calfrom = 'lmprun')
return {{'dp': 1, 'values.obj': {elastic_obj}, 'values.maxAE%': 55.0, 'values.MAE%': 54.0, 'values.Npt': 21}}
221.0 | stage 5 |  elastic   1.data (beta)
checkpoint: 1 constraints
| *  fail   'values.MAE% <= 30'  ->  '54.0 <= 30'
"""
    lines = "\n".join(f"# {ln}" for ln in stage.splitlines())
    return f"input {PARAMS}\n{lines}\n# 500000.0 | finalObj | done\n"


def test_tolerance_note_documents_placeholder():
    assert "0.01" in TOLERANCE_NOT_VALIDATED_NOTE
    assert "repeatability" in TOLERANCE_NOT_VALIDATED_NOTE.lower()


def test_worse_candidate_no_trigger(tmp_path: Path):
    rp = tmp_path / "ho.report"
    w = ElasticImprovementWatcher(rp, incumbent_elastic_obj=34.0, improvement_tolerance=0.01)
    rp.write_text(_elastic_trial_block(40.0))
    assert w.poll() is None


def test_equal_candidate_no_trigger(tmp_path: Path):
    rp = tmp_path / "ho.report"
    w = ElasticImprovementWatcher(rp, incumbent_elastic_obj=34.0, improvement_tolerance=0.01)
    rp.write_text(_elastic_trial_block(34.0))
    assert w.poll() is None


def test_below_tolerance_no_trigger(tmp_path: Path):
    rp = tmp_path / "ho.report"
    w = ElasticImprovementWatcher(rp, incumbent_elastic_obj=34.0, improvement_tolerance=0.01)
    rp.write_text(_elastic_trial_block(33.995))
    assert w.poll() is None


def test_meaningful_improvement_triggers(tmp_path: Path):
    rp = tmp_path / "ho.report"
    w = ElasticImprovementWatcher(rp, incumbent_elastic_obj=34.0, improvement_tolerance=0.01)
    rp.write_text(_elastic_trial_block(33.98))
    trig = w.poll()
    assert trig is not None
    assert trig.candidate_elastic_obj == pytest.approx(33.98)


def test_only_new_trials_evaluated(tmp_path: Path):
    rp = tmp_path / "ho.report"
    rp.write_text(_elastic_trial_block(40.0))
    w = ElasticImprovementWatcher(rp, incumbent_elastic_obj=34.0, improvement_tolerance=0.01)
    assert w.poll() is None
    rp.write_text(rp.read_text() + _elastic_trial_block(33.5))
    trig = w.poll()
    assert trig is not None
    assert trig.candidate_elastic_obj == pytest.approx(33.5)
