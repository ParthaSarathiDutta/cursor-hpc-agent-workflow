"""Elastic-priority RangeAgent trial selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from blast_lib.iterative_loop.ho_report_local import (
    NO_ELASTIC_CANDIDATE,
    best_elastic_trial_from_report,
    best_trial_from_report,
    select_trial_for_range,
)
from blast_lib.iterative_loop.selection_strategy import STRATEGY_ELASTIC, STRATEGY_OVERALL, load_selection_strategy
from blast_lib.parser import parse_ho_report

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "iter21750_stage_lines.txt"


def _mini_ho(*scores: tuple[int, float, str]) -> Path:
    """scores: (iteration, finalObj, stage_lines joined or use fixture for elastic)."""
    lines = ["input x\n"]
    for it, score, _ in scores:
        stage = "\n".join(f"# {ln}" for ln in FIXTURE.read_text().splitlines() if ln.strip())
        lines.append(f"input p\n{stage}\n# {score} | finalObj | reason\n")
    p = Path("/tmp") / "test_elastic_sel_ho.report"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(lines))
    return p


def test_load_strategy_defaults(tmp_path: Path):
    assert load_selection_strategy(tmp_path) == STRATEGY_OVERALL


def test_load_strategy_elastic(tmp_path: Path):
    (tmp_path / "strategy.json").write_text('{"selection_strategy": "elastic"}')
    assert load_selection_strategy(tmp_path) == STRATEGY_ELASTIC


def test_elastic_vs_overall_selector(tmp_path: Path):
    ho = _mini_ho((1, 995739.0, ""))
    overall = select_trial_for_range(ho, strategy=STRATEGY_OVERALL)
    elastic = select_trial_for_range(ho, strategy=STRATEGY_ELASTIC)
    assert overall["iteration"] == elastic["iteration"]


def test_no_elastic_raises(tmp_path: Path):
    ho = tmp_path / "ho.report"
    ho.write_text("input x\n# 1.0 | finalObj |\n")
    with pytest.raises(ValueError, match=NO_ELASTIC_CANDIDATE):
        best_elastic_trial_from_report(ho)
