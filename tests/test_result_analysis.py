"""ResultAnalysisAgent — read-only ho.report analysis."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from blast_lib.iterative_loop.ho_report_local import best_trial_from_report
from blast_lib.metrics import top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.result_analysis.metrics import absolute_error, percent_error
from blast_lib.result_analysis.plotting import build_comparison_result, write_error_heatmap
from blast_lib.result_analysis.query_router import parse_query
from blast_lib.result_analysis.result_analysis_agent import ResultAnalysisAgent, format_property_table
from blast_lib.result_analysis.result_parser import (
    analyze_best_from_report,
    analyze_iteration_from_report,
    trial_to_property_rows,
)
from blast_lib.trial_details import _elastic_constants, extract_target_pred_block

FIXTURE_LINES = (
    Path(__file__).resolve().parent / "fixtures" / "iter21750_stage_lines.txt"
).read_text().splitlines()


def _trial_from_fixture() -> dict:
    return {
        "iteration": 21750,
        "score": 995739.439343,
        "stage_lines": FIXTURE_LINES,
        "input_params": "Sb-Sb: 1 2 3",
        "reason": "1/1 elastic MAE% > 25",
    }


def test_lattice_multiline_extraction():
    block = extract_target_pred_block(FIXTURE_LINES, "lattice")
    assert block["headers"] == ["a", "b", "c", "alpha", "beta", "gamma"]
    assert len(block["targets"]) == 6
    assert len(block["predicted"]) == 6
    assert block["targets"][0] == pytest.approx(4.1162)
    assert block["predicted"][0] == pytest.approx(4.1547)
    assert block["predicted"][-1] == pytest.approx(120.0)


def test_cohesive_scalar_extraction():
    block = extract_target_pred_block(FIXTURE_LINES, "cohesive_E")
    assert block["headers"] == ["cohesive_energy"]
    assert block["targets"] == [pytest.approx(-2.61711)]
    assert block["predicted"] == [pytest.approx(-2.61722)]


def test_elastic_21_components():
    block = extract_target_pred_block(FIXTURE_LINES, "elastic")
    assert len(block["headers"]) == 21
    assert block["headers"][0] == "C11"
    assert block["headers"][-1] == "C56"
    assert len(block["targets"]) == 21
    assert len(block["predicted"]) == 21
    assert block["targets"][0] == pytest.approx(14.0)
    assert block["predicted"][0] == pytest.approx(6.26)
    assert block["targets"][3] == pytest.approx(3.0)
    assert block["predicted"][3] == pytest.approx(1.3216)


def test_elastic_constants_uses_shared_parser_subset():
    ec = _elastic_constants(FIXTURE_LINES)
    assert ec is not None
    assert "C11" in ec
    assert ec["C11"]["target"] == pytest.approx(14.0)


def test_percent_and_absolute_errors():
    assert absolute_error(14.0, 6.26) == pytest.approx(7.74)
    assert percent_error(14.0, 6.26) == pytest.approx(55.2857, rel=1e-3)
    assert percent_error(0.0, 1.0) is None


def test_trial_to_property_rows_counts(tmp_path: Path):
    rows = trial_to_property_rows(_trial_from_fixture())
    lattice = [r for r in rows if r.category == "lattice"]
    ce = [r for r in rows if r.category == "cohesive_energy"]
    elastic = [r for r in rows if r.category == "elastic"]
    assert len(lattice) == 6
    assert len(ce) == 1
    assert len(elastic) == 21
    zero_elastic = next(r for r in elastic if r.property_name == "C33")
    assert zero_elastic.target == 0
    assert zero_elastic.percent_error is None


def _ho_report_with_fixture(score: float) -> str:
    stage = "\n".join(f"# {line}" for line in FIXTURE_LINES if line.strip())
    return (
        "input bad\n# 1000000.0 | finalObj |\n"
        f"input good Sb\n{stage}\n# {score} | finalObj | reason\n"
    )


def test_best_from_mini_report(tmp_path: Path):
    ho = tmp_path / "reports" / "ho.report"
    ho.parent.mkdir(parents=True)
    ho.write_text(_ho_report_with_fixture(995739.439343))
    trials = parse_ho_report(ho)
    best = best_trial_from_report(ho)
    assert best["score"] == pytest.approx(995739.439343)
    assert top_k_trials(trials, k=1)[0]["iteration"] == best["iteration"]
    analyzed = analyze_best_from_report(ho)
    assert analyzed.final_obj == pytest.approx(995739.439343)


def test_analyze_set_invalid_iteration(tmp_path: Path):
    ho = tmp_path / "reports" / "ho.report"
    ho.parent.mkdir(parents=True)
    ho.write_text("input x\n# 1.0 | finalObj |\n")
    with pytest.raises(ValueError, match="No trial with iteration 999"):
        analyze_iteration_from_report(ho, 999)


def test_query_router():
    assert parse_query("show me the best set")[0] == "best"
    assert parse_query("show iteration 21750") == ("set", [21750])
    assert parse_query("compare 21750, 22000 and 23000") == (
        "compare",
        [21750, 22000, 23000],
    )


def test_compare_and_heatmap(tmp_path: Path):
    t = _trial_from_fixture()
    rows = trial_to_property_rows(t)
    from blast_lib.result_analysis.models import SetAnalysisResult

    s1 = SetAnalysisResult(1, 1.0, rows, "ho.report")
    s2 = SetAnalysisResult(2, 2.0, rows, "ho.report")
    comp = build_comparison_result([s1, s2])
    run = tmp_path / "run"
    run.mkdir()
    path = write_error_heatmap(comp, run_folder=run, filename="t.png")
    assert path.is_file()


def test_malformed_block_raises():
    with pytest.raises(ValueError):
        extract_target_pred_block(["score: lattice", "| t = [1]"], "lattice")


def test_agent_no_slurm_or_workflow_imports():
    import blast_lib.result_analysis.result_analysis_agent as mod

    source = inspect.getsource(mod)
    assert "scancel" not in source
    assert "workflow.json" not in source
    assert "submit_orchestrator" not in source
    assert "RangeAgent" not in source
    assert "ssh_exec" not in source


def test_agent_handle_query_best(tmp_path: Path):
    ho = tmp_path / "reports" / "ho.report"
    ho.parent.mkdir(parents=True)
    ho.write_text(_ho_report_with_fixture(995739.439343))
    agent = ResultAnalysisAgent(tmp_path)
    result = agent.handle_query("best set")
    assert result.iteration == 2
    assert result.final_obj == pytest.approx(995739.439343)
    assert len(result.properties) == 28
