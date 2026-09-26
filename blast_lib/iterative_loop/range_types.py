"""Shared types for range update (no SSH)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RangeUpdateResult:
    ok: bool
    message: str
    best_score: float | None = None
    best_iteration: int | None = None
    gpu_elapsed_sec: int | None = None
