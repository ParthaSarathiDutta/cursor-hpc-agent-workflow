"""Build property tables from ho.report trials."""

from __future__ import annotations

from pathlib import Path

from blast_lib.iterative_loop.ho_report_local import best_trial_from_report
from blast_lib.metrics import scored_trials
from blast_lib.parser import parse_ho_report
from blast_lib.result_analysis.metrics import absolute_error, percent_error
from blast_lib.result_analysis.models import PropertyResult, SetAnalysisResult
from blast_lib.result_analysis.phonon_parser import phonon_from_trial
from blast_lib.trial_details import extract_target_pred_block

_LATTICE_UNITS = {
    "a": "Å",
    "b": "Å",
    "c": "Å",
    "alpha": "°",
    "beta": "°",
    "gamma": "°",
}


def resolve_report_path(run_folder: str | Path) -> Path:
    folder = Path(run_folder)
    report = folder / "reports" / "ho.report"
    if report.is_file():
        return report
    raise FileNotFoundError(f"Missing ho.report under {folder}")


def trial_by_iteration(trials: list[dict], iteration: int) -> dict:
    for t in trials:
        if t.get("iteration") == iteration:
            return t
    raise ValueError(f"No trial with iteration {iteration} in ho.report")


def _rows_from_block(
    block: dict,
    *,
    category: str,
    unit_for_name,
) -> list[PropertyResult]:
    rows: list[PropertyResult] = []
    for name, t, p in zip(block["headers"], block["targets"], block["predicted"]):
        ae = absolute_error(t, p)
        pe = percent_error(t, p)
        rows.append(
            PropertyResult(
                property_name=name,
                target=t,
                predicted=p,
                absolute_error=ae,
                percent_error=round(pe, 4) if pe is not None else None,
                unit=unit_for_name(name),
                category=category,
            )
        )
    return rows


def _optional_target_pred_block(stage_lines: list[str], score_prefix: str) -> dict | None:
    try:
        return extract_target_pred_block(stage_lines, score_prefix)
    except ValueError as exc:
        if "No ho.report score block matching" in str(exc):
            return None
        raise


def trial_to_property_rows(trial: dict) -> list[PropertyResult]:
    lines = trial.get("stage_lines") or []
    rows: list[PropertyResult] = []

    lattice = _optional_target_pred_block(lines, "lattice")
    if lattice:
        rows.extend(
            _rows_from_block(
                lattice,
                category="lattice",
                unit_for_name=lambda n: _LATTICE_UNITS.get(n, ""),
            )
        )

    cohesive = _optional_target_pred_block(lines, "cohesive_E")
    if cohesive:
        rows.extend(
            _rows_from_block(
                cohesive,
                category="cohesive_energy",
                unit_for_name=lambda _n: "eV/atom",
            )
        )

    elastic = _optional_target_pred_block(lines, "elastic")
    if elastic:
        rows.extend(
            _rows_from_block(
                elastic,
                category="elastic",
                unit_for_name=lambda _n: "GPa",
            )
        )

    return rows


def analyze_trial_record(trial: dict, report_path: Path) -> SetAnalysisResult:
    return SetAnalysisResult(
        iteration=int(trial["iteration"]),
        final_obj=trial.get("score"),
        properties=trial_to_property_rows(trial),
        source_file=str(report_path.resolve()),
        input_params=(trial.get("input_params") or "").strip(),
        phonon=phonon_from_trial(trial),
    )


def analyze_best_from_report(report_path: Path) -> SetAnalysisResult:
    trial = best_trial_from_report(report_path)
    return analyze_trial_record(trial, report_path)


def analyze_iteration_from_report(report_path: Path, iteration: int) -> SetAnalysisResult:
    trials = parse_ho_report(report_path)
    trial = trial_by_iteration(trials, iteration)
    if trial.get("score") is None:
        raise ValueError(f"Trial iteration {iteration} has no finalObj score")
    return analyze_trial_record(trial, report_path)


def list_scored_iterations(report_path: Path, limit: int = 10) -> list[int]:
    trials = scored_trials(parse_ho_report(report_path))
    ranked = sorted(trials, key=lambda t: t["score"])[:limit]
    return [int(t["iteration"]) for t in ranked]
