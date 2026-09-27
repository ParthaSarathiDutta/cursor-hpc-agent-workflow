"""Error metrics for property comparison."""

from __future__ import annotations


def absolute_error(target: float, predicted: float) -> float:
    return abs(predicted - target)


def percent_error(target: float, predicted: float) -> float | None:
    if target == 0:
        return None
    return abs(predicted - target) / abs(target) * 100.0
