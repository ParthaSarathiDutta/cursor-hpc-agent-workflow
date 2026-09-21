"""Load and transform BLAST model.json searchable bounds."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from blast_lib.config import UIConfig
from blast_lib.remote import RemoteError, ssh_read_file

_BOUNDS_RE = re.compile(
    r"^\[(?P<lo>-?[\d.eE+-]+),\s*(?P<hi>-?[\d.eE+-]+)\]\s*(?P<fmt>%\.[\d]+[fg])?\s*$"
)


def _model_block(data: dict) -> dict[str, Any]:
    model = data.get("model") or {}
    if not model:
        raise ValueError("model.json missing 'model' key")
    return next(iter(model.values()))


def is_searchable_entry(value: str) -> bool:
    return bool(_BOUNDS_RE.match(value.strip()))


def searchable_keys(block: dict[str, Any]) -> list[str]:
    return [k for k, v in block.items() if isinstance(v, str) and is_searchable_entry(v)]


def parse_bounds_value(value: str) -> tuple[float, float, str]:
    m = _BOUNDS_RE.match(value.strip())
    if not m:
        raise ValueError(f"Not a bounds line: {value!r}")
    fmt = m.group("fmt") or "%.6f"
    return float(m.group("lo")), float(m.group("hi")), fmt


def format_bounds_value(lo: float, hi: float, fmt: str) -> str:
    f = fmt if fmt.startswith("%") else f"%{fmt}"
    return f"[{lo}, {hi}]  {f}"


def load_model_json_text(config: UIConfig, folder_path: str) -> str:
    from blast_lib.agenticblast_submit import normalize_run_path

    remote = normalize_run_path(config, folder_path)
    return ssh_read_file(config, f"{remote}/model.json")


def load_model_json(config: UIConfig, folder_path: str) -> dict:
    return json.loads(load_model_json_text(config, folder_path))


def render_model_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def merge_search_bounds(models: list[dict]) -> dict:
    if not models:
        raise ValueError("No models to merge")
    merged = deepcopy(models[0])
    block = _model_block(merged)
    keys = searchable_keys(block)
    for key in keys:
        los: list[float] = []
        his: list[float] = []
        fmt = "%.6f"
        for m in models:
            b = _model_block(m)
            if key not in b:
                continue
            lo, hi, fmt = parse_bounds_value(b[key])
            los.append(lo)
            his.append(hi)
        if los:
            block[key] = format_bounds_value(min(los), max(his), fmt)
    return merged


def tighten_bounds_around_vector(model: dict, param_vector: list[float], pct: float) -> dict:
    """Set each searchable bound to ±pct% around corresponding param value."""
    out = deepcopy(model)
    block = _model_block(out)
    keys = searchable_keys(block)
    if len(param_vector) < len(keys):
        raise ValueError(
            f"Parameter vector length {len(param_vector)} < searchable keys {len(keys)}"
        )
    scale = float(pct) / 100.0
    for i, key in enumerate(keys):
        v = float(param_vector[i])
        _, _, fmt = parse_bounds_value(block[key])
        if v == 0:
            delta = max(abs(v) * scale, 1e-6)
            new_lo, new_hi = v - delta, v + delta
        else:
            new_lo = v * (1.0 - scale)
            new_hi = v * (1.0 + scale)
        block[key] = format_bounds_value(new_lo, new_hi, fmt)
    return out


def tighten_bounds_from_trial(model: dict, trial_input_line: str, pct: float) -> dict:
    nums: list[float] = []
    for p in trial_input_line.split():
        try:
            nums.append(float(p))
        except ValueError:
            continue
    if not nums:
        raise ValueError("Trial input line has no numeric parameters")
    return tighten_bounds_around_vector(model, nums, pct)


def parse_mcts_restart_line(text: str, *, searchable_count: int | None = None) -> list[float]:
    nums: list[float] = []
    for token in text.strip().split():
        try:
            nums.append(float(token))
        except ValueError:
            continue
    if not nums:
        raise ValueError("No numeric values in mcts_restart.tersoff")
    if searchable_count and len(nums) >= searchable_count:
        nums = nums[-searchable_count:]
    elif len(nums) > 13:
        nums = nums[-13:]
    return nums


def format_mcts_restart_line(values: list[float]) -> str:
    return " ".join(f"{v:.6f}" for v in values) + "\n"


def read_mcts_restart_text(config: UIConfig, folder_path: str) -> str:
    from blast_lib.agenticblast_submit import normalize_run_path

    remote = normalize_run_path(config, folder_path)
    try:
        return ssh_read_file(config, f"{remote}/mcts_restart.tersoff")
    except RemoteError as exc:
        raise ValueError(f"Could not read mcts_restart.tersoff: {exc}") from exc
