"""Phonon reporting in ResultAnalysisAgent (read-only, ho.report fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.result_analysis.phonon_parser import phonon_from_trial
from blast_lib.result_analysis.result_analysis_agent import ResultAnalysisAgent, format_property_table
from blast_lib.result_analysis.result_parser import analyze_trial_record

PHONON_LINES = (
    Path(__file__).resolve().parent / "fixtures" / "phonon_iter2_block.txt"
).read_text().splitlines()

FIXTURE_LINES = (
    Path(__file__).resolve().parent / "fixtures" / "iter21750_stage_lines.txt"
).read_text().splitlines()


def _trial_with_phonon() -> dict:
    stage = FIXTURE_LINES + PHONON_LINES
    return {
        "iteration": 2,
        "score": 995739.439343,
        "stage_lines": stage,
        "input_params": "Sb-Sb: 1 2 3",
        "reason": "1/1 elastic MAE% > 25",
    }


def test_phonon_checkpoint_and_components():
    ph = phonon_from_trial(_trial_with_phonon())
    assert ph is not None
    assert ph.passed is True
    assert ph.checkpoint_metric == "ceil.maxAE%"
    assert ph.checkpoint_threshold == pytest.approx(30.20)
    assert "24.07" in (ph.checkpoint_actual or "")
    ceil = ph.components.get("ceil")
    assert ceil is not None
    assert ceil.max_ae_pct == pytest.approx(24.07)
    assert ceil.obj == pytest.approx(3.0829)
    assert ph.components["gap"].mae_pct == pytest.approx(3.08)


def test_phonon_scalars_and_vectors():
    ph = phonon_from_trial(_trial_with_phonon())
    assert ph is not None
    assert ph.gap_t == pytest.approx(2.338)
    assert ph.gap_p == pytest.approx(2.266)
    assert ph.gap_lo_t == pytest.approx(2.05003)
    assert ph.gap_lo_p == pytest.approx(2.05929)
    assert len(ph.ceil_t) == 6
    assert ph.ceil_t[0] == pytest.approx(1.2806)
    assert len(ph.ceil_p) == 6
    assert ph.ceil_p[-1] == pytest.approx(5.8675)
    assert len(ph.gamma_t) == 6
    assert len(ph.gamma_p) == 6


def test_analyze_set_includes_phonon(tmp_path: Path):
    ho = tmp_path / "reports" / "ho.report"
    ho.parent.mkdir(parents=True)
    stage = "\n".join(f"# {line}" for line in _trial_with_phonon()["stage_lines"] if line.strip())
    ho.write_text(f"input x\n{stage}\n# 995739.439343 | finalObj | reason\n")
    agent = ResultAnalysisAgent(tmp_path)
    result = agent.analyze_set(iteration=1)
    assert result.phonon is not None
    assert result.phonon.components["ceil"].max_ae_pct == pytest.approx(24.07)
    text = format_property_table(result)
    assert "Phonon score summary" in text
    assert "6-point phonon checkpoint-frequency comparison" in text
    assert "ceil_0" in text


def test_trial_without_phonon():
    trial = {
        "iteration": 1,
        "score": 1.0,
        "stage_lines": FIXTURE_LINES,
        "input_params": "",
    }
    assert phonon_from_trial(trial) is None
    rec = analyze_trial_record(trial, Path("/tmp/ho.report"))
    assert rec.phonon is None
