"""Plots for result comparison (read-only outputs under run folder)."""

from __future__ import annotations

from pathlib import Path

from blast_lib.result_analysis.models import ComparisonResult, SetAnalysisResult


def analysis_output_dir(run_folder: str | Path) -> Path:
    path = Path(run_folder) / ".agentic_loop" / "analysis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_error_heatmap(
    comparison: ComparisonResult,
    *,
    run_folder: str | Path,
    filename: str = "compare_heatmap.png",
) -> Path:
    import matplotlib.pyplot as plt
    import numpy as np

    out_dir = analysis_output_dir(run_folder)
    out_path = out_dir / filename

    prop_names = comparison.property_names
    set_labels = [str(s.iteration) for s in comparison.sets]
    matrix = comparison.error_matrix

    masked = np.array(
        [[np.nan if v is None else v for v in row] for row in matrix],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=(max(6, len(set_labels) * 1.2), max(5, len(prop_names) * 0.25)))
    im = ax.imshow(masked, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(set_labels)))
    ax.set_xticklabels(set_labels, rotation=45, ha="right")
    ax.set_yticks(range(len(prop_names)))
    ax.set_yticklabels(prop_names, fontsize=8)
    metric = comparison.heatmap_metric.replace("_", " ")
    ax.set_title(f"Property error heatmap ({metric})")
    fig.colorbar(im, ax=ax, label=metric)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def build_comparison_result(
    sets: list[SetAnalysisResult],
    *,
    use_percent: bool = True,
) -> ComparisonResult:
    """Align properties across sets; matrix uses percent_error or absolute_error."""
    prop_order: list[str] = []
    seen: set[str] = set()
    for s in sets:
        for p in s.properties:
            if p.property_name not in seen:
                seen.add(p.property_name)
                prop_order.append(p.property_name)

    matrix: list[list[float | None]] = []
    for pname in prop_order:
        row: list[float | None] = []
        for s in sets:
            match = next((p for p in s.properties if p.property_name == pname), None)
            if match is None:
                row.append(None)
            elif use_percent and match.percent_error is not None:
                row.append(match.percent_error)
            else:
                row.append(match.absolute_error)
        matrix.append(row)

    metric = "percent_error" if use_percent else "absolute_error"
    return ComparisonResult(
        sets=sets,
        property_names=prop_order,
        error_matrix=matrix,
        heatmap_metric=metric,
    )
