"""Bar plots from comparison CSV outputs."""

from __future__ import annotations

import csv
from pathlib import Path

from blast_lib.property_comparison.config import (
    ELASTIC_ERRORS_SOURCE_CSV,
    ELASTIC_SOURCE_CSV,
    ComparisonConfig,
)

TARGET_COLOR = "#333333"


def _load_csv(comp: Path, name: str) -> list[dict[str, str]]:
    with (comp / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def _f(s: str) -> float:
    return float(s) if s and s.strip() else float("nan")


def _rows_by_property(comp: Path) -> dict[str, dict[str, str]]:
    with (comp / "property_comparison.csv").open(newline="") as fh:
        return {r["Property"]: r for r in csv.DictReader(fh)}


def plot_all(config: ComparisonConfig) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    comp = config.comparison_dir
    labels = config.labels
    colors = config.plot_colors
    n = len(labels)
    width_group = min(0.18, 0.8 / max(n, 1))

    by = _rows_by_property(comp)
    lat_props = [f"lattice_{n}" for n, _u in [("a", ""), ("b", ""), ("c", ""), ("alpha", ""), ("beta", ""), ("gamma", "")]]
    lat_labels = ["a", "b", "c", "alpha", "beta", "gamma"]

    # Lattice errors
    x = np.arange(len(lat_props))
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, label in enumerate(labels):
        vals = [_f(by[p].get(f"{label} error %", "")) for p in lat_props]
        ax.bar(x + (i - (n - 1) / 2) * width_group, vals, width_group, label=label, color=colors[i % len(colors)])
    ax.set_ylabel("Error %")
    ax.set_title("Lattice property errors")
    ax.set_xticks(x)
    ax.set_xticklabels(lat_labels)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(comp / "barplot_lattice_errors.png", dpi=150)
    plt.close(fig)

    # Lattice target vs predicted
    series = ["Target"] + labels
    ns = len(series)
    w = min(0.11, 0.85 / ns)
    fig, ax = plt.subplots(figsize=(12, 5))
    for si, slabel in enumerate(series):
        vals = [_f(by[p].get(slabel, "")) for p in lat_props]
        color = TARGET_COLOR if slabel == "Target" else colors[labels.index(slabel) % len(colors)]
        ax.bar(x + (si - (ns - 1) / 2) * w, vals, w, label=slabel, color=color)
    ax.set_ylabel("Value (Å or deg)")
    ax.set_title("Lattice: target vs predicted")
    ax.set_xticks(x)
    ax.set_xticklabels(lat_labels)
    ax.legend(fontsize=7, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(comp / "barplot_lattice_target_vs_predicted.png", dpi=150)
    plt.close(fig)

    # Cohesive error
    row = by["cohesive_energy"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, [_f(row.get(f"{l} error %", "")) for l in labels], color=[colors[i % len(colors)] for i in range(n)])
    ax.set_ylabel("Cohesive energy error %")
    ax.set_title("Cohesive energy comparison")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(comp / "barplot_cohesive_error.png", dpi=150)
    plt.close(fig)

    # Cohesive target vs predicted
    bl = ["Target"] + labels
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(bl, [_f(row.get(l, "")) for l in bl], color=[TARGET_COLOR] + [colors[i % len(colors)] for i in range(n)])
    ax.set_ylabel("Cohesive energy (eV)")
    ax.set_title("Cohesive energy: target vs predicted")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(comp / "barplot_cohesive_target_vs_predicted.png", dpi=150)
    plt.close(fig)

    elastic = config.elastic_constants
    err_rows = {r["Property"]: r for r in _load_csv(comp, ELASTIC_ERRORS_SOURCE_CSV)}
    tp_rows = {r["Property"]: r for r in _load_csv(comp, ELASTIC_SOURCE_CSV)}
    x = np.arange(len(elastic))

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, label in enumerate(labels):
        key = f"{label} Error %"
        vals = [_f(err_rows[p].get(key, "")) for p in elastic]
        ax.bar(x + (i - (n - 1) / 2) * width_group, vals, width_group, label=label, color=colors[i % len(colors)])
    ax.set_ylabel("Absolute error (%)")
    ax.set_title("Elastic constants — error comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(list(elastic))
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(comp / "barplot_elastic_errors.png", dpi=150)
    plt.close(fig)

    series = ["Target"] + labels
    ns = len(series)
    w = min(0.13, 0.85 / ns)
    fig, ax = plt.subplots(figsize=(10, 5))
    for si, slabel in enumerate(series):
        vals = [_f(tp_rows[p].get(slabel, "")) for p in elastic]
        color = TARGET_COLOR if slabel == "Target" else colors[labels.index(slabel) % len(colors)]
        ax.bar(x + (si - (ns - 1) / 2) * w, vals, w, label=slabel, color=color)
    ax.set_ylabel("Elastic constant (GPa)")
    ax.set_title("Elastic: target vs predicted")
    ax.set_xticks(x)
    ax.set_xticklabels(list(elastic))
    ax.legend(fontsize=7, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(comp / "barplot_elastic_target_vs_predicted.png", dpi=150)
    plt.close(fig)
