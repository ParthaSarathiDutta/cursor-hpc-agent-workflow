"""Write comparison CSV files (physical properties only)."""

from __future__ import annotations

import csv
from typing import Any

from blast_lib.changemodel_bounds import PARAMETERS as TERSOFF_PARAMS
from blast_lib.property_comparison.config import (
    ELASTIC_ERRORS_SOURCE_CSV,
    ELASTIC_SOURCE_CSV,
    LATTICE_LABELS,
    ComparisonConfig,
)
from blast_lib.property_comparison.extract import (
    cohesive_pair,
    elastic_subset,
    input_param_tokens,
    lattice_data,
    load_snapshots,
)
from blast_lib.property_comparison.formatting import abs_err, fmt, fmt_pct, pct_err
from blast_lib.trial_details import extract_target_pred_block


def build_elastic_tables(
    snaps: dict[str, dict[str, Any]],
    config: ComparisonConfig,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    labels = config.labels
    tp_rows: list[dict[str, str]] = []
    err_rows: list[dict[str, str]] = []
    for name in config.elastic_constants:
        t_ref: float | None = None
        tp_row: dict[str, str] = {"Property": name}
        err_row: dict[str, str] = {"Property": name}
        for label in labels:
            t, p = elastic_subset(snaps[label]["_trial"], config.elastic_constants)[name]
            if t_ref is None and t is not None:
                t_ref = t
            tp_row[label] = fmt(p)
            err_row[f"{label} Error %"] = fmt_pct(pct_err(t_ref if t_ref is not None else t, p))
        tp_row["Target"] = fmt(t_ref)
        tp_rows.append(tp_row)
        err_rows.append(err_row)
    return tp_rows, err_rows


def write_property_comparison(
    snaps: dict[str, dict[str, Any]],
    config: ComparisonConfig,
    tp_rows: list[dict[str, str]],
) -> None:
    labels = config.labels
    rows: list[dict[str, str]] = []
    targets, preds_lat = lattice_data(snaps, labels)
    for i, (name, unit) in enumerate(LATTICE_LABELS):
        t = targets[i] if i < len(targets) else None
        row: dict[str, str] = {"Property": f"lattice_{name}", "Unit": unit, "Target": fmt(t)}
        for label in labels:
            p = preds_lat[label][i] if i < len(preds_lat.get(label, [])) else None
            row[label] = fmt(p)
            row[f"{label} error %"] = fmt_pct(pct_err(t, p))
        rows.append(row)

    t_ce: float | None = None
    row_ce: dict[str, str] = {"Property": "cohesive_energy", "Unit": "eV", "Target": ""}
    for label in labels:
        t, p = cohesive_pair(snaps[label]["_trial"])
        if t_ce is None and t is not None:
            t_ce = t
        row_ce[label] = fmt(p)
        row_ce[f"{label} error %"] = fmt_pct(pct_err(t_ce, p))
    row_ce["Target"] = fmt(t_ce)
    rows.append(row_ce)

    for tp in tp_rows:
        row = {"Property": f"elastic_{tp['Property']}", "Unit": "GPa", "Target": tp["Target"]}
        for label in labels:
            t = float(tp["Target"]) if tp.get("Target") else None
            p = float(tp[label]) if tp.get(label) else None
            row[label] = tp.get(label, "")
            row[f"{label} error %"] = fmt_pct(pct_err(t, p))
        rows.append(row)

    fields = ["Property", "Unit", "Target"]
    for label in labels:
        fields.extend([label, f"{label} error %"])
    path = config.comparison_dir / "property_comparison.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_per_set_csvs(snaps: dict[str, dict[str, Any]], config: ComparisonConfig) -> None:
    fields = ["Property", "Category", "Target", "Predicted", "Absolute Error", "Error %", "Unit"]
    for spec in config.potentials:
        label = spec.label
        trial = snaps[label]["_trial"]
        out_rows: list[dict[str, str]] = []
        if trial:
            try:
                block = extract_target_pred_block(trial.get("stage_lines") or [], "lattice")
                for (name, unit), t, p in zip(LATTICE_LABELS, block["targets"], block["predicted"]):
                    out_rows.append(
                        {
                            "Property": name,
                            "Category": "lattice",
                            "Target": fmt(t),
                            "Predicted": fmt(p),
                            "Absolute Error": fmt(abs_err(t, p)),
                            "Error %": fmt_pct(pct_err(t, p)),
                            "Unit": unit,
                        }
                    )
            except ValueError:
                pass
            t, p = cohesive_pair(trial)
            if t is not None:
                out_rows.append(
                    {
                        "Property": "cohesive_energy",
                        "Category": "cohesive_energy",
                        "Target": fmt(t),
                        "Predicted": fmt(p),
                        "Absolute Error": fmt(abs_err(t, p)),
                        "Error %": fmt_pct(pct_err(t, p)),
                        "Unit": "eV",
                    }
                )
            for cname, (t, p) in elastic_subset(trial, config.elastic_constants).items():
                out_rows.append(
                    {
                        "Property": cname,
                        "Category": "elastic",
                        "Target": fmt(t),
                        "Predicted": fmt(p),
                        "Absolute Error": fmt(abs_err(t, p)),
                        "Error %": fmt_pct(pct_err(t, p)),
                        "Unit": "GPa",
                    }
                )
        out_path = config.comparison_dir / spec.per_set_path()
        with out_path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(out_rows)


def write_parameter_csv(snaps: dict[str, dict[str, Any]], config: ComparisonConfig) -> None:
    labels = config.labels
    cols = ["Parameter"] + labels
    rows: list[dict[str, str]] = []
    m_row: dict[str, str] = {
        "Parameter": "m (fixed; not one of the 13 optimized CLI parameters)",
    }
    for spec in config.potentials:
        if spec.fixed_m is not None:
            m_row[spec.label] = spec.fixed_m
        else:
            m_row[spec.label] = "—"
    rows.append(m_row)
    for i, pname in enumerate(TERSOFF_PARAMS):
        row = {"Parameter": pname}
        for spec in config.potentials:
            label = spec.label
            trial = snaps[label]["_trial"]
            if trial:
                parts = input_param_tokens(trial)
                row[label] = parts[i] if len(parts) > i else "—"
            elif spec.parameter_vector and len(spec.parameter_vector) > i:
                row[label] = spec.parameter_vector[i]
            else:
                row[label] = "—"
        rows.append(row)
    with (config.comparison_dir / "parameter_comparison.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def write_elastic_sources(
    config: ComparisonConfig,
    tp_rows: list[dict[str, str]],
    err_rows: list[dict[str, str]],
) -> None:
    labels = config.labels
    tp_fields = ["Property", "Target"] + labels
    err_fields = ["Property"] + [f"{l} Error %" for l in labels]
    comp = config.comparison_dir
    comp.mkdir(parents=True, exist_ok=True)
    with (comp / ELASTIC_SOURCE_CSV).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=tp_fields)
        w.writeheader()
        w.writerows(tp_rows)
    with (comp / ELASTIC_ERRORS_SOURCE_CSV).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=err_fields)
        w.writeheader()
        w.writerows(err_rows)


def build_all(config: ComparisonConfig) -> dict[str, Any]:
    config.comparison_dir.mkdir(parents=True, exist_ok=True)
    snaps = load_snapshots(config.workspace, config.potentials)
    tp_rows, err_rows = build_elastic_tables(snaps, config)
    write_elastic_sources(config, tp_rows, err_rows)
    write_property_comparison(snaps, config, tp_rows)
    write_per_set_csvs(snaps, config)
    write_parameter_csv(snaps, config)
    return {"snapshots": snaps, "elastic_tp": tp_rows, "elastic_err": err_rows}
