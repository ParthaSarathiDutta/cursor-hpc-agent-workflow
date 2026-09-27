"""Read-only analysis of BLAST ho.report results (independent of iterative loop).

Does not submit/cancel Slurm jobs or mutate NERSC workflow state files.
"""

from __future__ import annotations

from pathlib import Path

from blast_lib.result_analysis.models import ComparisonResult, SetAnalysisResult
from blast_lib.result_analysis.plotting import (
    build_comparison_result,
    write_error_heatmap,
)
from blast_lib.result_analysis.query_router import parse_query
from blast_lib.result_analysis.result_parser import (
    analyze_best_from_report,
    analyze_iteration_from_report,
    resolve_report_path,
)


class ResultAnalysisAgent:
    """Analyze synced ho.report data only — no Slurm or workflow state writes."""

    def __init__(self, run_folder: str | Path) -> None:
        self.run_folder = Path(run_folder)
        self.report_path = resolve_report_path(self.run_folder)

    def analyze_best(self) -> SetAnalysisResult:
        return analyze_best_from_report(self.report_path)

    def analyze_set(self, *, iteration: int) -> SetAnalysisResult:
        return analyze_iteration_from_report(self.report_path, iteration)

    def compare_sets(self, iterations: list[int]) -> ComparisonResult:
        sets = [self.analyze_set(iteration=i) for i in iterations]
        comparison = build_comparison_result(sets)
        heatmap = write_error_heatmap(
            comparison,
            run_folder=self.run_folder,
            filename=f"compare_{'_'.join(str(i) for i in iterations)}.png",
        )
        comparison.heatmap_path = str(heatmap)
        return comparison

    def handle_query(self, query: str) -> SetAnalysisResult | ComparisonResult:
        action, ids = parse_query(query)
        if action == "best":
            return self.analyze_best()
        if action == "set":
            assert ids is not None
            return self.analyze_set(iteration=ids[0])
        assert ids is not None
        return self.compare_sets(ids)


def format_property_table(result: SetAnalysisResult) -> str:
    """Human-readable Property | Target | Predicted | Abs Error | Error % table."""
    lines = [
        f"iteration={result.iteration} finalObj={result.final_obj}",
        f"source: {result.source_file}",
        "",
        "Property | Target | Predicted | Absolute Error | Error % | Unit",
        "---|---|---|---|---|---",
    ]
    for p in result.properties:
        pe = "N/A" if p.percent_error is None else f"{p.percent_error:.4f}"
        lines.append(
            f"{p.property_name} | {p.target} | {p.predicted} | {p.absolute_error} | {pe} | {p.unit}"
        )
    return "\n".join(lines)
