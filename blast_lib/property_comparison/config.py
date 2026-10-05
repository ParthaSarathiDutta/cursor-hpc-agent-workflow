"""Comparison workspace configuration (JSON)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ELASTIC = ("C11", "C22", "C12", "C66")

LATTICE_LABELS = [
    ("a", "Å"),
    ("b", "Å"),
    ("c", "Å"),
    ("alpha", "deg"),
    ("beta", "deg"),
    ("gamma", "deg"),
]

ELASTIC_SOURCE_CSV = "elastic_plot_source.csv"
ELASTIC_ERRORS_SOURCE_CSV = "elastic_errors_source.csv"


@dataclass
class PotentialSpec:
    run_dir: str
    label: str
    per_set_csv: str | None = None
    parameter_vector: list[str] | None = None
    """Optional 13 Tersoff CLI values when ho.report is absent (parameter table only)."""
    fixed_m: str | None = None
    """If set, shown in parameter_comparison.csv m row for this column."""

    def per_set_path(self) -> str:
        if self.per_set_csv:
            return self.per_set_csv
        safe = self.run_dir.replace("/", "_")
        return f"{safe}_target_vs_predicted.csv"


@dataclass
class ComparisonConfig:
    workspace: Path
    comparison_subdir: str = "comparison"
    elastic_constants: tuple[str, ...] = DEFAULT_ELASTIC
    potentials: list[PotentialSpec] = field(default_factory=list)
    plot_colors: list[str] = field(
        default_factory=lambda: ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD"]
    )

    @property
    def comparison_dir(self) -> Path:
        return self.workspace / self.comparison_subdir

    @property
    def labels(self) -> list[str]:
        return [p.label for p in self.potentials]

    @classmethod
    def from_dict(cls, data: dict[str, Any], config_path: Path | None = None) -> ComparisonConfig:
        ws = Path(data["workspace"])
        if not ws.is_absolute() and config_path is not None:
            ws = (config_path.parent / ws).resolve()
        potentials = [
            PotentialSpec(
                run_dir=p["run_dir"],
                label=p["label"],
                per_set_csv=p.get("per_set_csv"),
                parameter_vector=p.get("parameter_vector"),
                fixed_m=p.get("fixed_m"),
            )
            for p in data.get("potentials", [])
        ]
        elastic = tuple(data.get("elastic_constants", list(DEFAULT_ELASTIC)))
        return cls(
            workspace=ws,
            comparison_subdir=data.get("comparison_subdir", "comparison"),
            elastic_constants=elastic,
            potentials=potentials,
            plot_colors=list(
                data.get("plot_colors", ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD"])
            ),
        )


def load_config(path: Path) -> ComparisonConfig:
    data = json.loads(path.read_text())
    return ComparisonConfig.from_dict(data, config_path=path)
