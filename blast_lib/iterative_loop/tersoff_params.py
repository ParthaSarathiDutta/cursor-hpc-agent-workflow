"""Pure Tersoff parameter / mcts_restart helpers (no SSH)."""

from __future__ import annotations

import re

from blast_lib.changemodel_bounds import TERSEOFF_PARAM_COUNT

DEFAULT_SB_PREFIX = "Sb Sb Sb 1"
_FLOAT_RE = re.compile(r"-?[\d]+(?:\.[\d]*)?(?:[eE][+-]?\d+)?")


def extract_tersoff_param_strings(input_params: str) -> list[str]:
    text = input_params.strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    tokens = _FLOAT_RE.findall(text)
    if len(tokens) < TERSEOFF_PARAM_COUNT:
        raise ValueError(
            f"Expected {TERSEOFF_PARAM_COUNT} parameters in input line, found {len(tokens)}"
        )
    return tokens[-TERSEOFF_PARAM_COUNT:]


def extract_tersoff_floats(input_params: str) -> list[float]:
    return [float(x) for x in extract_tersoff_param_strings(input_params)]


def split_mcts_restart_line(text: str) -> tuple[str, list[float]]:
    parts = text.strip().split()
    if len(parts) < TERSEOFF_PARAM_COUNT:
        raise ValueError("mcts_restart.tersoff too short")
    floats = [float(x) for x in parts[-TERSEOFF_PARAM_COUNT:]]
    prefix = " ".join(parts[:-TERSEOFF_PARAM_COUNT]).strip() or DEFAULT_SB_PREFIX
    return prefix, floats


def format_mcts_restart_line(prefix: str, values: list[float]) -> str:
    if len(values) != TERSEOFF_PARAM_COUNT:
        raise ValueError(f"Need {TERSEOFF_PARAM_COUNT} values for mcts_restart")
    nums = " ".join(f"{v:.6f}" for v in values)
    return f"{prefix} {nums}\n"
