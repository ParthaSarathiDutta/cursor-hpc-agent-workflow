"""Run-folder selection strategy for RangeAgent (explicit config, not folder-name magic)."""

from __future__ import annotations

import json
from pathlib import Path

STRATEGY_OVERALL = "overall"
STRATEGY_ELASTIC = "elastic"
VALID_STRATEGIES = frozenset({STRATEGY_OVERALL, STRATEGY_ELASTIC})


def strategy_json_path(run_folder: Path) -> Path:
    return run_folder / "strategy.json"


def load_selection_strategy(run_folder: Path) -> str:
    """Default overall (min finalObj); elastic child folders set strategy.json."""
    path = strategy_json_path(run_folder)
    if not path.is_file():
        return STRATEGY_OVERALL
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return STRATEGY_OVERALL
    strategy = (data.get("selection_strategy") or STRATEGY_OVERALL).strip().lower()
    if strategy in VALID_STRATEGIES:
        return strategy
    return STRATEGY_OVERALL
