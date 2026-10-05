"""Tests for blast_lib.property_comparison."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from blast_lib.property_comparison.build import build_all
from blast_lib.property_comparison.config import ComparisonConfig, PotentialSpec, load_config
from blast_lib.property_comparison.formatting import fmt
from blast_lib.property_comparison.plot import plot_all
from blast_lib.property_comparison.validate import validate_outputs

ELASTIC_BLOCK = """
score: elastic ['values']
| header: C11 C22 C33 C12 C13 C23 C44 C55 C66
| t = [ 14.  14.   0.   3.   0.   0.   0.   0.   5.]
| p = [ 10.  8.   0.   2.   0.   0.   0.   0.   3.]
return {'values.obj': 99.0, 'values.MAE%': 25.0}
""".strip()

LATTICE_BLOCK = """
score: lattice
| header: a b c alpha beta gamma
| t = [ 4.0 4.0 30.0 90.0 90.0 120.0]
| p = [ 4.1 4.1 30.0 90.0 90.0 120.0]
return {'values.MAE%': 1.0}
""".strip()

CE_BLOCK = """
score: cohesive_E
| t = -2.5
| p = -2.6
return {'values.MAE%': 2.0}
""".strip()


def _write_trial(report: Path, tag: str, c11_p: float) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    elastic = ELASTIC_BLOCK.replace("| p = [ 10.", f"| p = [ {c11_p}.")
    body = "\n".join(
        [
            f"input Sb-Sb: {tag}",
            *[f"# {line}" for line in LATTICE_BLOCK.splitlines()],
            *[f"# {line}" for line in CE_BLOCK.splitlines()],
            *[f"# {line}" for line in elastic.splitlines()],
            f"# 100.0 | finalObj | {tag} DUMP elastic",
        ]
    )
    report.write_text(body + "\n")


def _workspace(tmp_path: Path, n: int = 4) -> ComparisonConfig:
    for i in range(n):
        run = tmp_path / f"pot_{i}"
        _write_trial(run / "reports" / "ho.report", f"tag{i}", 10.0 + i)
    potentials = [
        PotentialSpec(run_dir=f"pot_{i}", label=f"Custom-{i}") for i in range(n)
    ]
    return ComparisonConfig(workspace=tmp_path, comparison_subdir="comparison", potentials=potentials)


def test_arbitrary_potential_labels(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 4)
    build_all(cfg)
    with (cfg.comparison_dir / "property_comparison.csv").open(newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        assert all(f"Custom-{i}" in reader.fieldnames for i in range(4))


def test_fourth_potential_not_dropped(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 4)
    build_all(cfg)
    with (cfg.comparison_dir / "elastic_plot_source.csv").open(newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["Custom-3"].strip() != ""


def test_missing_elastic_reported_not_zero(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 2)
    (cfg.workspace / "pot_1" / "reports" / "ho.report").unlink()
    build_all(cfg)
    assert fmt(None) == ""
    errs = validate_outputs(cfg, require_elastic_values=True)
    assert any("missing" in e.lower() or "empty" in e.lower() for e in errs)


def test_elastic_constants_configurable(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 2)
    cfg.elastic_constants = ("C11", "C66")
    build_all(cfg)
    with (cfg.comparison_dir / "property_comparison.csv").open(newline="") as fh:
        elastic = [r["Property"] for r in csv.DictReader(fh) if r["Property"].startswith("elastic_")]
    assert elastic == ["elastic_C11", "elastic_C66"]


def test_main_csv_excludes_objectives(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 2)
    build_all(cfg)
    text = (cfg.comparison_dir / "property_comparison.csv").read_text()
    assert "finalObj" not in text
    assert "values.obj" not in text


def test_per_set_csv(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 1)
    cfg.potentials[0].per_set_csv = "alpha_target_vs_predicted.csv"
    build_all(cfg)
    path = cfg.comparison_dir / "alpha_target_vs_predicted.csv"
    assert path.is_file()
    rows = list(csv.DictReader(path.open()))
    assert any(r["Category"] == "elastic" and r["Property"] == "C11" for r in rows)


def test_plot_reads_csv(tmp_path: Path) -> None:
    cfg = _workspace(tmp_path, 2)
    build_all(cfg)
    plot_all(cfg)
    assert (cfg.comparison_dir / "barplot_elastic_errors.png").is_file()


def test_load_example_config() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts/property_comparison/examples/tersoff_4pot_comparison.json"
    cfg = load_config(path)
    assert len(cfg.potentials) == 4
    assert cfg.labels[-1] == "Published ML-Tersoff"
    assert "ML-Tersoff-1" not in cfg.labels
