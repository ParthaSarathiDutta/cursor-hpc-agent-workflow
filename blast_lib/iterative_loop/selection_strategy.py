"""Run-folder strategy config for RangeAgent and orchestrator (explicit, not folder-name magic)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from blast_lib.iterative_loop.recenter_trigger import (
    DEFAULT_IMPROVEMENT_TOLERANCE,
    DEFAULT_MAX_REGIONS,
    RECENTER_FIXED_CYCLE,
    RECENTER_IMPROVEMENT,
    VALID_RECENTER_TRIGGERS,
)

STRATEGY_OVERALL = "overall"
STRATEGY_ELASTIC = "elastic"
VALID_STRATEGIES = frozenset({STRATEGY_OVERALL, STRATEGY_ELASTIC})


def strategy_json_path(run_folder: Path) -> Path:
    return run_folder / "strategy.json"


@dataclass(frozen=True)
class StrategyConfig:
    selection_strategy: str = STRATEGY_OVERALL
    recenter_trigger: str = RECENTER_FIXED_CYCLE
    improvement_tolerance: float = DEFAULT_IMPROVEMENT_TOLERANCE
    incumbent_elastic_obj: float | None = None
    max_regions: int = DEFAULT_MAX_REGIONS
    max_total_runtime_sec: int | None = None


def _parse_strategy_payload(data: dict) -> StrategyConfig:
    selection = (data.get("selection_strategy") or STRATEGY_OVERALL).strip().lower()
    if selection not in VALID_STRATEGIES:
        selection = STRATEGY_OVERALL

    recenter = (data.get("recenter_trigger") or RECENTER_FIXED_CYCLE).strip().lower()
    if recenter not in VALID_RECENTER_TRIGGERS:
        recenter = RECENTER_FIXED_CYCLE

    tol_raw = data.get("improvement_tolerance", DEFAULT_IMPROVEMENT_TOLERANCE)
    try:
        tolerance = float(tol_raw)
    except (TypeError, ValueError):
        tolerance = DEFAULT_IMPROVEMENT_TOLERANCE

    incumbent_raw = data.get("incumbent_elastic_obj")
    incumbent: float | None
    if incumbent_raw is None or incumbent_raw == "":
        incumbent = None
    else:
        try:
            incumbent = float(incumbent_raw)
        except (TypeError, ValueError):
            incumbent = None

    max_regions_raw = data.get("max_regions", DEFAULT_MAX_REGIONS)
    try:
        max_regions = int(max_regions_raw)
    except (TypeError, ValueError):
        max_regions = DEFAULT_MAX_REGIONS
    max_regions = max(1, max_regions)

    max_rt: int | None = None
    if data.get("max_total_runtime") is not None:
        max_rt = _walltime_or_seconds(data.get("max_total_runtime"))
    elif data.get("max_total_runtime_sec") is not None:
        try:
            max_rt = int(data["max_total_runtime_sec"])
        except (TypeError, ValueError):
            max_rt = None

    return StrategyConfig(
        selection_strategy=selection,
        recenter_trigger=recenter,
        improvement_tolerance=tolerance,
        incumbent_elastic_obj=incumbent,
        max_regions=max_regions,
        max_total_runtime_sec=max_rt,
    )


def _walltime_or_seconds(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        from blast_lib.iterative_loop.slurm_timing import parse_walltime_seconds

        return parse_walltime_seconds(text)
    try:
        return int(text)
    except ValueError:
        return None


def strategy_config_from_dict(data: dict) -> StrategyConfig:
    if not isinstance(data, dict):
        return StrategyConfig()
    return _parse_strategy_payload(data)


def load_strategy_config(run_folder: Path) -> StrategyConfig:
    path = strategy_json_path(run_folder)
    if not path.is_file():
        return StrategyConfig()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return StrategyConfig()
    if not isinstance(data, dict):
        return StrategyConfig()
    return _parse_strategy_payload(data)


def load_selection_strategy(run_folder: Path) -> str:
    """Default overall (min finalObj); elastic child folders set strategy.json."""
    return load_strategy_config(run_folder).selection_strategy


def is_improvement_elastic_strategy(cfg: StrategyConfig) -> bool:
    return (
        cfg.selection_strategy == STRATEGY_ELASTIC
        and cfg.recenter_trigger == RECENTER_IMPROVEMENT
    )
