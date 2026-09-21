"""Parse checkpoint thresholds from run-folder main1.py."""

from __future__ import annotations

import re

from blast_lib.config import UIConfig
from blast_lib.remote import RemoteError, ssh_exec
from blast_lib.user_session import local_cache_dir

STAGE_ORDER = ["lattice", "ce", "eos", "phonon", "elastic"]

_PROP_RE = re.compile(r"""^\s*prop\s*=\s*['"](\w+)['"]""")
_CHECKPOINT_RE = re.compile(r"\.checkpoint\s*\(")
_CONDITION_RE = re.compile(r'"([^"]*(?:<=|>=|==|!=|<|>)[^"]*)"')


def _normalize_stage(name: str) -> str:
    n = name.lower()
    if n in ("cohesive_e", "cohesive", "cohesiveenergy"):
        return "ce"
    return n


def parse_main1_checkpoints(source: str) -> dict[str, list[str]]:
    """Extract active checkpoint condition strings keyed by property stage."""
    stages: dict[str, list[str]] = {}
    current_prop: str | None = None
    lines = source.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        prop_m = _PROP_RE.match(line)
        if prop_m:
            current_prop = _normalize_stage(prop_m.group(1))

        if _CHECKPOINT_RE.search(line):
            block_lines = [line]
            j = i
            while "]" not in block_lines[-1] and j + 1 < len(lines):
                j += 1
                block_lines.append(lines[j])

            stage = current_prop
            block_text = "\n".join(block_lines)
            if re.search(r"\.checkpoint\s*\(\s*['\"]phonon['\"]", block_text):
                stage = "phonon"
            elif re.search(r"\.checkpoint\s*\(\s*prop", block_text) and current_prop:
                stage = current_prop

            if not stage:
                i = j + 1
                continue

            conditions: list[str] = []
            for bl in block_lines:
                stripped = bl.strip()
                if stripped.startswith("#"):
                    continue
                code = bl.split("#", 1)[0]
                for m in _CONDITION_RE.finditer(code):
                    cond = m.group(1).strip()
                    if cond and cond not in conditions:
                        conditions.append(cond)

            if conditions:
                bucket = stages.setdefault(stage, [])
                for c in conditions:
                    if c not in bucket:
                        bucket.append(c)

            i = j + 1
            continue

        i += 1

    return {s: stages[s] for s in STAGE_ORDER if s in stages}


def _resolve_run_path(config: UIConfig, run_path: str) -> str:
    text = run_path.strip()
    if text.startswith("/"):
        return text.rstrip("/")
    return f"{config.blast_root.rstrip('/')}/{text}"


def load_main1_text(config: UIConfig, run_path: str) -> str | None:
    remote = _resolve_run_path(config, run_path)
    cached = local_cache_dir(config, remote) / "main1.py"
    if cached.is_file():
        return cached.read_text()
    try:
        text = ssh_exec(config, f"cat '{remote}/main1.py'", timeout=20)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(text)
        return text
    except RemoteError:
        return None


def load_main1_checkpoints(config: UIConfig, run_path: str) -> dict[str, list[str]]:
    text = load_main1_text(config, run_path)
    if not text:
        return {}
    return parse_main1_checkpoints(text)


_THRESHOLD_RE = re.compile(
    r"((?:values\.maxAE%|maxAE%?|ceil\.maxAE%|ordering\.Norderoff==0,\s*values\.maxAE%)[^\"]*?[<>=!]+\s*)([\d.]+)"
)


def _replace_condition_threshold(condition: str, pct: float) -> str:
    m = _THRESHOLD_RE.search(condition)
    if m and float(m.group(2)) == float(pct):
        return condition
    return _THRESHOLD_RE.sub(rf"\g<1>{pct:g}", condition, count=1)


_NUM_LIMIT_RE = re.compile(r"(<=\s*)([\d.]+)\s*$")


def parse_checkpoint_limits(source: str) -> dict[str, float]:
    """Extract absolute checkpoint limits from main1.py (eos shape/shift, phonon ceil, elastic MAE)."""
    parsed = parse_main1_checkpoints(source)
    out: dict[str, float] = {}
    for cond in parsed.get("eos", []):
        if "shape.obj" in cond:
            m = _NUM_LIMIT_RE.search(cond.replace(" ", ""))
            if m:
                out["eos_shape_obj"] = float(m.group(2))
        if "shift.obj" in cond:
            m = _NUM_LIMIT_RE.search(cond.replace(" ", ""))
            if m:
                out["eos_shift_obj"] = float(m.group(2))
    for cond in parsed.get("phonon", []):
        if "ceil.maxAE%" in cond:
            m = _NUM_LIMIT_RE.search(cond)
            if m:
                out["phonon_ceil_maxae"] = float(m.group(2))
    for cond in parsed.get("elastic", []):
        if "values.MAE%" in cond:
            m = _NUM_LIMIT_RE.search(cond)
            if m:
                out["elastic_mae_pct"] = float(m.group(2))
    return out


def parse_maxae_percentages(source: str) -> dict[str, float]:
    """maxAE% tolerances for lattice and ce from parsed checkpoint strings."""
    parsed = parse_main1_checkpoints(source)
    out: dict[str, float] = {}
    for stage in ("lattice", "ce"):
        for cond in parsed.get(stage, []):
            if "maxAE%" not in cond:
                continue
            m = re.search(r"maxAE%\s*<=\s*([\d.]+)", cond.replace(" ", ""))
            if m:
                out[stage] = float(m.group(1))
                break
    return out


def _replace_numeric_limit(condition: str, new_value: float) -> str:
    m = _NUM_LIMIT_RE.search(condition)
    if m and float(m.group(2)) == float(new_value):
        return condition
    return _NUM_LIMIT_RE.sub(rf"\g<1>{new_value:g}", condition, count=1)


def apply_checkpoint_limits(source: str, limits: dict[str, float]) -> tuple[str, list[str]]:
    """Update absolute checkpoint thresholds (eos shape/shift.obj, phonon ceil, elastic MAE%)."""
    parsed = parse_main1_checkpoints(source)
    updated = source
    missing: list[str] = []
    key_to_substr = {
        "eos_shape_obj": ("eos", "shape.obj"),
        "eos_shift_obj": ("eos", "shift.obj"),
        "phonon_ceil_maxae": ("phonon", "ceil.maxAE%"),
        "elastic_mae_pct": ("elastic", "values.MAE%"),
    }
    for key, value in limits.items():
        stage, needle = key_to_substr.get(key, (None, None))
        if not stage:
            continue
        conds = parsed.get(stage, [])
        matched = False
        for old_cond in conds:
            if needle not in old_cond.replace(" ", ""):
                continue
            new_cond = _replace_numeric_limit(old_cond, float(value))
            if new_cond != old_cond:
                updated = updated.replace(old_cond, new_cond)
            matched = True
        if not matched:
            missing.append(key)
    return updated, missing


def apply_checkpoint_percentages(source: str, pct_by_stage: dict[str, float]) -> tuple[str, list[str]]:
    """
    Update checkpoint condition thresholds in main1.py for given stages.
    Returns (new_source, stages_not_found_in_file).
    """
    parsed = parse_main1_checkpoints(source)
    updated = source
    missing: list[str] = []
    for stage, pct in pct_by_stage.items():
        st = _normalize_stage(stage)
        if st in ("eos",):
            continue
        if st not in parsed or not parsed[st]:
            missing.append(st)
            continue
        for old_cond in parsed[st]:
            new_cond = _replace_condition_threshold(old_cond, pct)
            if new_cond != old_cond:
                updated = updated.replace(old_cond, new_cond)
    return updated, missing


def format_checkpoint_config(checkpoint_config: dict[str, list[str]]) -> str:
    if not checkpoint_config:
        return "Configured checkpoints (main1.py): not available — Sync folder or check SSH."
    lines = ["Configured checkpoints (from main1.py):"]
    for stage in STAGE_ORDER:
        rules = checkpoint_config.get(stage)
        if rules:
            lines.append(f"  - {stage}: {'; '.join(rules)}")
    return "\n".join(lines)
