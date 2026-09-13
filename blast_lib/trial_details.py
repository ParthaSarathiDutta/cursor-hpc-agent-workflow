"""Extract granular metrics from ho.report stage lines."""

from __future__ import annotations

import ast
import re
from typing import Any

from blast_lib.main1_checkpoints import format_checkpoint_config

RETURN_RE = re.compile(r"return\s+(\{.*\})")
CHECKPOINT_RE = re.compile(r"\|\s*(?:\*?\s*)?(pass|fail)\s+'([^']+)'\s+->\s+'([^']+)'", re.I)
STAGE_LINE_RE = re.compile(r"(?:sub)?stage\s+([\d.a-z]+)\s*\|\s*(.+)", re.I)
SCORE_LINE_RE = re.compile(r"score:\s*(\w+)\s*(?:\[(.*?)\])?", re.I)
COMPONENTS_RE = re.compile(r"\+?\s*'([^']+)'")
POLYMORPH_RE = re.compile(r"(\d+)\.data", re.I)
ELASTIC_HEADER_RE = re.compile(r"header:\s*(.+)", re.I)

FOLDER_PROPERTY_LADDER = "lattice → ce → eos → phonon → elastic"

FOLDER_POLYMORPHS: dict[str, dict[str, str]] = {
    "ML-Tersoff-1_PE": {s: "[0]" for s in ("lattice", "ce", "eos", "phonon", "elastic")},
    "ML-Tersoff-1_PE_12": {s: "[0, 1]" for s in ("lattice", "ce", "eos", "phonon", "elastic")},
    "ML-Tersoff-1_PE_hybrid": {
        "lattice": "[0]",
        "ce": "[0, 1]",
        "eos": "[0]",
        "phonon": "[0]",
        "elastic": "[0]",
    },
}

STAGE_ORDER = ["lattice", "ce", "eos", "phonon", "elastic"]

METRIC_GLOSSARY = """Metric glossary (from ho.report return dicts — names vary by stage):
- lattice / elastic / simple stages: values.MAE%, values.maxAE%, values.obj
- ce: values.* plus ordering.obj (relative energy ordering across polymorphs)
- eos: shape.obj, shape.MAE%, shape.maxAE% (curve shape); shift.obj, shift.MAE% (energy shift)
- phonon: ceil.maxAE%, ceil.MAE%, ceil.obj (acoustic ceiling frequencies);
  gap/shape/gamma/neg components also scored — see score components line
Checkpoints list the pass/fail rule and actual value (e.g. ceil.maxAE% <= 30.20).
Each trial includes **Tersoff parameters** on the ho.report `input` line (e.g. `Sb-Sb: r0 r1 E1 ...`).
"""


def _parse_return_dict(text: str) -> dict[str, Any] | None:
    m = RETURN_RE.search(text.replace("\n", " "))
    if not m:
        return None
    try:
        return ast.literal_eval(m.group(1))
    except (SyntaxError, ValueError):
        return None


def _normalize_stage(name: str) -> str:
    n = name.lower()
    if n in ("cohesive_e", "cohesive", "cohesiveenergy"):
        return "ce"
    return n


def _group_metrics(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for key, val in metrics.items():
        if "." in key:
            prefix, suffix = key.split(".", 1)
        else:
            prefix, suffix = "_root", key
        groups.setdefault(prefix, {})[suffix] = val
    return groups


def _format_metric_groups(groups: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for prefix in sorted(groups):
        parts = [f"{k}={v}" for k, v in sorted(groups[prefix].items())]
        label = prefix if prefix != "_root" else "metrics"
        lines.append(f"    {label}: {', '.join(parts)}")
    return lines


def _pick_block_label(stage_lines_in_chunk: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """Prefer polymorph substage lines over aggregate 'from a,b' summary lines."""
    if not stage_lines_in_chunk:
        return None, None
    polymorph = [(sid, lbl) for sid, lbl in stage_lines_in_chunk if POLYMORPH_RE.search(lbl)]
    if polymorph:
        return polymorph[-1]
    non_missing = [(sid, lbl) for sid, lbl in stage_lines_in_chunk if "missing" not in lbl.lower()]
    non_agg = [(sid, lbl) for sid, lbl in non_missing if "from a,b" not in lbl.lower()]
    if non_agg:
        return non_agg[-1]
    return stage_lines_in_chunk[-1]


def _stage_from_substage_id(substage_id: str | None) -> str | None:
    if not substage_id:
        return None
    m = re.match(r"(\d+)", substage_id)
    if not m:
        return None
    idx = int(m.group(1))
    if 1 <= idx <= len(STAGE_ORDER):
        return STAGE_ORDER[idx - 1]
    return None


def _append_missing_substage_blocks(stage_lines: list[str], blocks: list[dict[str, Any]]) -> None:
    """Add blocks for substages marked missing (e.g. phonon 2.data never computed)."""
    existing = {(b.get("substage"), b.get("stage")) for b in blocks}
    for line in stage_lines:
        m = STAGE_LINE_RE.search(line)
        if not m or "missing" not in m.group(2).lower():
            continue
        sid, label = m.group(1), m.group(2).strip()
        stage = _stage_from_substage_id(sid)
        if not stage or (sid, stage) in existing:
            continue
        blocks.append(
            {
                "stage": stage,
                "substage": sid,
                "label": label,
                "polymorph_index": None,
                "score_components": [],
                "metrics": {},
                "metric_groups": {},
                "checkpoints": [],
                "passed": None,
                "missing": True,
            }
        )
        existing.add((sid, stage))


def parse_property_blocks(stage_lines: list[str]) -> list[dict[str, Any]]:
    """Split ho.report stage lines into scored property blocks (one per polymorph substage)."""
    chunks = re.split(r"(?=score:\s*)", "\n".join(stage_lines))
    blocks: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or not chunk.lower().startswith("score:"):
            continue

        sm = SCORE_LINE_RE.search(chunk)
        if not sm:
            continue
        stage = _normalize_stage(sm.group(1))
        bracket = sm.group(2) or ""
        components = [c.strip().strip("'\"") for c in re.findall(r"'([^']+)'", bracket)]

        plus_line = next((ln for ln in chunk.splitlines() if ln.strip().startswith("+")), "")
        if plus_line:
            components = COMPONENTS_RE.findall(plus_line) or components

        metrics = _parse_return_dict(chunk) or {}
        stage_lines_in_chunk = STAGE_LINE_RE.findall(chunk)
        substage_id, label = _pick_block_label(stage_lines_in_chunk)
        label = (label or "").strip()
        polymorph_idx = None
        pm = POLYMORPH_RE.search(label)
        if pm:
            polymorph_idx = int(pm.group(1)) - 1

        checkpoints = [
            {"result": m.group(1).lower(), "rule": m.group(2), "actual": m.group(3)}
            for m in CHECKPOINT_RE.finditer(chunk)
        ]
        failed = any(c["result"] == "fail" for c in checkpoints)
        passed = bool(checkpoints) and not failed

        blocks.append(
            {
                "stage": stage,
                "substage": substage_id,
                "label": label,
                "polymorph_index": polymorph_idx,
                "score_components": components,
                "metrics": metrics,
                "metric_groups": _group_metrics(metrics),
                "checkpoints": checkpoints,
                "passed": passed if checkpoints else None,
                "missing": "missing" in label.lower(),
            }
        )

    _append_missing_substage_blocks(stage_lines, blocks)
    return blocks


def _elastic_constants(stage_lines: list[str]) -> dict[str, dict[str, float]] | None:
    header: list[str] = []
    targets: list[float] = []
    preds: list[float] = []
    in_elastic = False

    for line in stage_lines:
        if "score: elastic" in line.lower():
            in_elastic = True
            continue
        if not in_elastic:
            continue
        if SCORE_LINE_RE.search(line) and "elastic" not in line.lower():
            break
        hm = ELASTIC_HEADER_RE.search(line)
        if hm:
            header = hm.group(1).split()
            continue
        if line.strip().startswith("| t ="):
            targets = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)]
            continue
        if line.strip().startswith("| p ="):
            preds = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)]
            continue

    if not header or not targets or not preds:
        return None

    n = min(len(header), len(targets), len(preds))
    out: dict[str, dict[str, float]] = {}
    for i in range(n):
        t, p = targets[i], preds[i]
        if t == 0 and p == 0:
            continue
        pct = abs(p - t) / abs(t) * 100 if t else 0.0
        out[header[i]] = {"target": t, "predicted": p, "error_pct": round(pct, 2)}
    return out or None


def analyze_trial(trial: dict, folder_name: str) -> dict[str, Any]:
    stage_lines = trial.get("stage_lines") or []
    blocks = parse_property_blocks(stage_lines)
    polymorphs = FOLDER_POLYMORPHS.get(folder_name, {})

    by_stage: dict[str, list[dict[str, Any]]] = {s: [] for s in STAGE_ORDER}
    for block in blocks:
        if block["stage"] in by_stage:
            by_stage[block["stage"]].append(block)

    stages_summary = []
    for name in STAGE_ORDER:
        stage_blocks = by_stage[name]
        if not stage_blocks:
            continue
        last = stage_blocks[-1]
        ret = last.get("metrics") or {}
        cps: list[dict] = []
        for b in stage_blocks:
            cps.extend(b.get("checkpoints") or [])
        failed = any(c["result"] == "fail" for c in cps)
        stages_summary.append(
            {
                "stage": name,
                "polymorphs": polymorphs.get(name, "?"),
                "blocks": stage_blocks,
                "mae_pct": ret.get("values.MAE%"),
                "max_ae_pct": ret.get("values.maxAE%"),
                "passed": not failed if cps else None,
                "checkpoints": cps,
            }
        )

    return {
        "property_ladder": FOLDER_PROPERTY_LADDER,
        "polymorphs_by_stage": polymorphs,
        "property_blocks": blocks,
        "stages": stages_summary,
        "elastic_constants": _elastic_constants(stage_lines),
        "failure_reason": trial.get("reason"),
    }


def analyze_best_trial(trial: dict, folder_name: str) -> dict[str, Any]:
    return analyze_trial(trial, folder_name)


def _format_block(block: dict[str, Any], configured_rules: list[str] | None = None) -> list[str]:
    lines: list[str] = []
    poly = block.get("polymorph_index")
    poly_txt = f"polymorph [{poly}]" if poly is not None else "polymorph [?]"
    label = block.get("label") or block["stage"]
    if block.get("missing"):
        sub = block.get("substage") or "?"
        lines.append(f"  - substage {sub} | {label}: **not computed**")
        return lines

    lines.append(f"  - {label} ({poly_txt}):")
    if block.get("score_components"):
        lines.append(f"      score components: {', '.join(block['score_components'])}")
    lines.extend(_format_metric_groups(block.get("metric_groups") or {}))

    trial_cps = block.get("checkpoints") or []
    if trial_cps:
        for cp in trial_cps:
            mark = "PASS" if cp["result"] == "pass" else "FAIL"
            lines.append(f"      trial {mark}: {cp['rule']} → {cp['actual']}")
    elif configured_rules:
        lines.append(f"      trial: (no checkpoint result in ho.report — thresholds: {'; '.join(configured_rules)})")

    return lines


def format_property_detail(analysis: dict[str, Any], checkpoint_config: dict[str, list[str]] | None = None) -> str:
    """Full per-property / per-polymorph breakdown for chat context."""
    cfg = checkpoint_config or {}
    lines: list[str] = []
    for stage_info in analysis.get("stages", []):
        name = stage_info["stage"]
        configured = cfg.get(name, [])
        header = f"  **{name}** (configured polymorphs {stage_info['polymorphs']})"
        if configured:
            header += f"\n      thresholds (main1.py): {'; '.join(configured)}"
        lines.append(header)
        for block in stage_info.get("blocks") or []:
            lines.extend(_format_block(block, configured))
        if name == "elastic":
            ec = analysis.get("elastic_constants")
            if ec:
                lines.append("      elastic constants (DFT vs LAMMPS):")
                for cname, vals in sorted(ec.items()):
                    lines.append(
                        f"        {cname}: target={vals['target']}, pred={vals['predicted']}, error={vals['error_pct']}%"
                    )
        lines.append("")
    return "\n".join(lines).rstrip()


def recommend_next_action(folder_name: str, best_stage: str, analysis: dict[str, Any]) -> str:
    if best_stage == "elastic":
        mae = max_ae = threshold = None
        for s in analysis.get("stages", []):
            if s["stage"] == "elastic":
                mae, max_ae = s.get("mae_pct"), s.get("max_ae_pct")
                for cp in s.get("checkpoints", []):
                    if "MAE%" in cp["rule"]:
                        threshold = cp["rule"]
                break
        detail = f" elastic MAE%={mae}, maxAE%={max_ae}" if mae is not None else ""
        th = f" (checkpoint: {threshold})" if threshold else ""
        return (
            f"**{folder_name}:** Best set reached elastic; failed{detail}{th}. "
            "Seed from **this folder's** best trial → `changemodel.json.py` ±10% → MCTS restart here."
        )
    if best_stage == "phonon":
        fail_cp = ""
        for s in analysis.get("stages", []):
            if s["stage"] == "phonon":
                for cp in s.get("checkpoints", []):
                    if cp["result"] == "fail":
                        fail_cp = f" Failed checkpoint: {cp['rule']} → {cp['actual']}."
        return (
            f"**{folder_name}:** Best set stopped at phonon.{fail_cp} "
            "Seed from **this folder's** best trial → ±10% → MCTS restart here — not another folder's seed."
        )
    if best_stage in ("ce", "lattice", "eos"):
        return (
            f"**{folder_name}:** Best set stopped at {best_stage}. "
            "Seed from **this folder's** best trial → ±10% → MCTS restart here."
        )
    if best_stage == "complete":
        return f"**{folder_name}:** Completed all stages — update `mcts_restart.tersoff`."
    return f"**{folder_name}:** Analyze after syncing ho.report."


def format_trial_params(trial: dict) -> str:
    params = (trial.get("input_params") or "").strip()
    if not params:
        return "Tersoff parameters: (missing from ho.report input line)"
    return f"Tersoff parameters (input line): {params}"


def _format_stage_compact(stage_info: dict[str, Any], configured_rules: list[str] | None = None) -> str:
    """One-line stage summary with metrics and trial checkpoint results."""
    parts: list[str] = []
    for block in stage_info.get("blocks") or []:
        if block.get("missing"):
            parts.append("missing substage")
            continue
        mg = block.get("metric_groups") or {}
        for prefix, vals in sorted(mg.items()):
            if prefix == "_root":
                continue
            key_bits = []
            for k in ("MAE%", "maxAE%", "obj", "Npt"):
                if k in vals:
                    key_bits.append(f"{prefix}.{k}={vals[k]}")
            if key_bits:
                parts.append(", ".join(key_bits))
        for cp in block.get("checkpoints") or []:
            mark = "pass" if cp["result"] == "pass" else "FAIL"
            parts.append(f"{mark}: {cp['rule']} → {cp['actual']}")

    if not parts and configured_rules:
        parts.append("thresholds: " + "; ".join(configured_rules))

    status = "pass" if stage_info.get("passed") else "FAIL" if stage_info.get("passed") is False else "?"
    body = "; ".join(parts) if parts else "no metrics"
    return f"{stage_info['stage']}: {status} ({body})"


def format_trial_compact(
    folder_name: str,
    trial: dict,
    rank: int,
    checkpoint_config: dict[str, list[str]] | None = None,
) -> str:
    analysis = analyze_trial(trial, folder_name)
    cfg = checkpoint_config or {}
    stage = trial.get("stage") or "unknown"
    lines = [
        f"#### Rank {rank} — iteration {trial.get('iteration')}, score={trial.get('score')}, deepest stage={stage}",
        format_trial_params(trial),
        f"Outcome: {(trial.get('reason') or '')[:120]}",
    ]
    for s in analysis.get("stages", []):
        lines.append(f"  {_format_stage_compact(s, cfg.get(s['stage']))}")
    return "\n".join(lines)


def format_analysis_text(
    folder_name: str,
    trial: dict,
    analysis: dict[str, Any],
    checkpoint_config: dict[str, list[str]] | None = None,
) -> str:
    cfg = checkpoint_config or {}
    lines = [
        f"### {folder_name}",
        f"Property order: {analysis['property_ladder']}",
        "",
        format_checkpoint_config(cfg) if cfg else "Configured checkpoints (main1.py): not loaded",
        "",
        "Polymorphs per property stage:",
    ]
    for stage, poly in analysis["polymorphs_by_stage"].items():
        lines.append(f"  - {stage}: {poly}")

    lines.extend(
        [
            "",
            f"Best set outcome: {analysis.get('failure_reason')}",
            format_trial_params(trial),
            "",
            "Detailed property performance (metrics + checkpoints, per polymorph when present):",
            format_property_detail(analysis, cfg),
            "",
            "Recommended next action:",
            recommend_next_action(folder_name, trial.get("stage", "unknown"), analysis),
        ]
    )
    return "\n".join(lines)
