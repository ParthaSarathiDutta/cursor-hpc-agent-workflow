"""Validate comparison CSV outputs."""

from __future__ import annotations

import csv

from blast_lib.property_comparison.config import ELASTIC_SOURCE_CSV, ComparisonConfig


def validate_outputs(config: ComparisonConfig, *, require_elastic_values: bool = True) -> list[str]:
    errors: list[str] = []
    labels = config.labels
    elastic_props = {f"elastic_{c}" for c in config.elastic_constants}
    path = config.comparison_dir / "property_comparison.csv"
    if not path.is_file():
        return [f"Missing {path}"]

    found_elastic: set[str] = set()
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            prop = row["Property"]
            if "finalObj" in prop or ".obj" in prop:
                errors.append(f"Internal objective in main CSV: {prop}")
            if prop.startswith("elastic_"):
                found_elastic.add(prop)
                if prop not in elastic_props:
                    errors.append(f"Unexpected elastic row: {prop}")
                if require_elastic_values:
                    for label in labels:
                        if not row.get(label, "").strip():
                            errors.append(f"{prop}: missing prediction for {label}")
                        if not row.get(f"{label} error %", "").strip():
                            errors.append(f"{prop}: missing error % for {label}")

    if found_elastic != elastic_props:
        errors.append(f"Elastic rows mismatch: got {found_elastic}, expected {elastic_props}")

    src = config.comparison_dir / ELASTIC_SOURCE_CSV
    if src.is_file() and require_elastic_values:
        with src.open(newline="") as fh:
            for row in csv.DictReader(fh):
                for label in labels:
                    if not row.get(label, "").strip():
                        errors.append(f"{ELASTIC_SOURCE_CSV} {row['Property']}: empty {label}")

    if "Published ML-Tersoff-1" in labels:
        errors.append("Published ML-Tersoff-1 must be excluded from config")

    return errors
