"""Display formatting for CSV outputs."""

from __future__ import annotations

from typing import Any


def pct_err(t: float | None, p: float | None) -> float | None:
    if t is None or p is None or t == 0:
        return None
    return abs(p - t) / abs(t) * 100.0


def abs_err(t: float | None, p: float | None) -> float | None:
    if t is None or p is None:
        return None
    return abs(p - t)


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def fmt_pct(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else ""
